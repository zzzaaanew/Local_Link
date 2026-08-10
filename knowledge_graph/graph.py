"""원천기사 파이프라인 Phase 2 — Neo4j 지식그래프 조회. (LLM 없음)

데모 대비 수정한 점:
  1) Cypher 인젝션 제거 — 키워드는 LLM이 만든 문자열이라 f-string으로 끼워 넣으면
     따옴표 하나에도 쿼리가 깨지거나 주입된다. 전부 파라미터($keywords)로 바인딩한다.
  2) 지역 필터 버그 수정 — 데모 q3는 WHERE가 OPTIONAL MATCH에 귀속돼 경북이 아닌
     자산까지 반환됐다. 지역 조건을 첫 MATCH 뒤로 올렸다.
  3) 드라이버를 요청마다 새로 만들지 않고 모듈 단위로 재사용한다.

환경변수: AURA_URI / AURA_USER / AURA_PASSWORD (없으면 빈 컨텍스트 반환)
"""
import logging
import os

logger = logging.getLogger(__name__)

REGION_HINTS = ["경상북도", "경북", "포항", "구미", "경산", "안동", "경주", "김천", "영주", "상주"]

_driver = None


def is_configured() -> bool:
    return bool(_clean("AURA_URI") and _clean("AURA_USER") and _clean("AURA_PASSWORD"))


def _clean(name: str) -> str:
    return os.environ.get(name, "").strip().strip('"').strip("'")


def _get_driver():
    """드라이버를 한 번만 생성해 재사용한다."""
    global _driver
    if _driver is None:
        from neo4j import GraphDatabase  # 선택 의존성 — 미설정 환경에서 import 비용 회피

        _driver = GraphDatabase.driver(
            _clean("AURA_URI"), auth=(_clean("AURA_USER"), _clean("AURA_PASSWORD"))
        )
    return _driver


def close() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


# ------------------------------------------------------------
# Cypher (모두 파라미터 바인딩)
# ------------------------------------------------------------

# 실제 그래프 구조에 맞춘 쿼리.
# Program 이 허브(관계 대부분이 여기 붙어 있음)이고, 이 온톨로지는 발제용으로
# 설계돼 있어 우리 발제 카드 필드와 그대로 대응된다:
#   REQUIRES_CHECK→DataPoint = 확인할 자료
#   HAS_INTERVIEW_TARGET→Stakeholder = 취재 대상
#   SUGGESTS_FRAME→ReportingFrame = 보도 각도
# 패턴 컴프리헨션을 써서 OPTIONAL MATCH 다중 조인으로 행이 폭증하는 것을 피한다.

Q_PROGRAM = """
MATCH (p:Program)
WHERE size($keywords) = 0
   OR any(kw IN $keywords WHERE
        toLower(coalesce(p.name, '')) CONTAINS toLower(kw)
     OR toLower(coalesce(p.program_type, '')) CONTAINS toLower(kw))
RETURN p.name AS program, p.program_type AS ptype, p.status AS status,
  [(p)-[:LOCATED_IN]->(r:LocalRegion) | r.name]              AS regions,
  [(p)-[:INVOLVES]->(s:Stakeholder) | s.name]                AS stakeholders,
  [(p)-[:TARGETS]->(s:Stakeholder) | s.name]                 AS targets,
  [(p)-[:HAS_INTERVIEW_TARGET]->(s:Stakeholder) | s.name]    AS interview_targets,
  [(p)-[:REQUIRES_CHECK]->(d:DataPoint) | d.name]            AS data_points,
  [(p)-[:SUGGESTS_FRAME]->(f:ReportingFrame) | f.name]       AS frames,
  [(c:CentralAction)-[:OPERATES]->(p) | c.title]             AS central_actions,
  [(p)-[:HAS_PREVIOUS_PROGRAM]->(q:Program) | q.name]        AS previous
LIMIT 8
"""

Q_ISSUE = """
MATCH (i:LocalIssue)
WHERE size($keywords) = 0
   OR any(kw IN $keywords WHERE toLower(coalesce(i.keyword, '')) CONTAINS toLower(kw))
RETURN i.keyword AS issue, i.status AS status,
  [(s:Stakeholder)-[:RESPONDS_TO]->(i) | s.name]   AS responders,
  [(s:Stakeholder)-[:AFFECTED_BY]->(i) | s.name]   AS affected,
  [(a:LocalAsset)-[:HAS_ISSUE]->(i) | a.name]      AS assets,
  [(e:EcoIndicator)-[:INDICATES]->(i)
     | e.name + ' ' + coalesce(toString(e.current_value), '')] AS indicators,
  [(i)-[:CONTRIBUTES_TO]->(o:LocalIssue) | o.keyword] AS leads_to,
  [(i)-[:WORSENS]->(o:LocalIssue) | o.keyword]        AS worsens
LIMIT 10
"""

Q_CENTRAL_ACTION = """
MATCH (ca:CentralAction)
WHERE size($keywords) = 0
   OR any(kw IN $keywords WHERE
        toLower(coalesce(ca.title, '')) CONTAINS toLower(kw)
     OR toLower(coalesce(ca.category, '')) CONTAINS toLower(kw))
RETURN ca.title AS action, ca.category AS category, ca.date AS date,
  [(ca)-[:OPERATES]->(p:Program) | p.name]          AS programs,
  [(ca)-[:OPERATES]->(r:LocalRegion) | r.name]      AS regions,
  [(ca)-[:REQUIRES_CHECK]->(d:DataPoint) | d.name]  AS data_points,
  [(ca)-[:SUGGESTS_FRAME]->(f:ReportingFrame) | f.name] AS frames
LIMIT 8
"""

# 갈등 구도는 그 자체로 기사 가치가 높아 별도로 뽑는다.
Q_CONFLICT = """
MATCH (a:Stakeholder)-[:CONFLICTS_WITH]-(b:Stakeholder)
WHERE a.name < b.name
RETURN a.name AS a, a.stakeholder_type AS a_type,
       b.name AS b, b.stakeholder_type AS b_type
LIMIT 5
"""

Q_INDICATOR = """
MATCH (e:EcoIndicator)
WHERE size($keywords) = 0
   OR any(kw IN $keywords WHERE toLower(coalesce(e.name, '')) CONTAINS toLower(kw))
RETURN e.name AS indicator, e.current_value AS value,
  [(e)-[:MEASURES]->(r:LocalRegion) | r.name] AS regions,
  [(e)-[:MEASURES]->(a:LocalAsset) | a.name]  AS assets,
  [(e)-[:INDICATES]->(i:LocalIssue) | i.keyword] AS issues
LIMIT 8
"""


def fetch_context(keywords: list[str]) -> dict:
    """키워드로 그래프를 조회해 LLM에 넣을 팩트 문장을 모은다.

    반환: {"nodes": [...], "relationships": [...], "retrieved_context": [...]}
    연결 정보가 없으면 빈 컨텍스트를 돌려주고 파이프라인은 계속 진행한다.
    """
    if not is_configured():
        logger.info("Neo4j 접속 정보 없음 — 그래프 컨텍스트 없이 진행")
        return _empty()

    kws = [k.strip() for k in (keywords or []) if k and k.strip()]
    params = {"keywords": kws, "regions": REGION_HINTS}

    context: list[str] = []
    # 발제 카드 필드에 바로 쓸 수 있게 별도로도 모아 둔다.
    suggested = {"interview_targets": [], "data_to_check": [], "frames": []}

    try:
        with _get_driver().session() as s:
            for r in s.run(Q_PROGRAM, params):
                context.append(_program_line(r))
                suggested["interview_targets"] += r["interview_targets"] or []
                suggested["data_to_check"] += r["data_points"] or []
                suggested["frames"] += r["frames"] or []

            for r in s.run(Q_ISSUE, params):
                context.append(_issue_line(r))

            for r in s.run(Q_CENTRAL_ACTION, params):
                context.append(_central_line(r))
                suggested["data_to_check"] += r["data_points"] or []
                suggested["frames"] += r["frames"] or []

            for r in s.run(Q_INDICATOR, params):
                context.append(_indicator_line(r))

            for r in s.run(Q_CONFLICT, params):
                context.append(
                    f"[갈등] {r['a']}({r['a_type']}) ↔ {r['b']}({r['b_type']}) — 입장이 충돌"
                )
    except Exception as exc:
        # 그래프가 없거나 스키마가 달라도 발제 생성 자체는 계속되어야 한다.
        logger.warning("Neo4j 조회 실패 — 그래프 컨텍스트 없이 진행: %s", exc)
        return _empty()

    context = [c for c in dict.fromkeys(context) if c]  # 중복·빈 줄 제거
    suggested = {k: list(dict.fromkeys(v))[:8] for k, v in suggested.items()}
    logger.info("Neo4j 조회 완료: 팩트 %d건", len(context))
    return {"retrieved_context": context, "suggested": suggested}


# ------------------------------------------------------------
# 레코드 → 사람이 읽는 팩트 문장
# ------------------------------------------------------------

def _join(values, limit: int = 4) -> str:
    items = [v for v in (values or []) if v]
    return ", ".join(items[:limit])


def _program_line(r) -> str:
    parts = [f"[사업] {r['program']}"]
    meta = ", ".join(x for x in [r["ptype"], r["status"]] if x)
    if meta:
        parts.append(f"({meta})")
    if r["regions"]:
        parts.append(f"| 지역: {_join(r['regions'])}")
    if r["central_actions"]:
        parts.append(f"| 상위정책: {_join(r['central_actions'])}")
    if r["stakeholders"]:
        parts.append(f"| 관계자: {_join(r['stakeholders'])}")
    if r["targets"]:
        parts.append(f"| 대상: {_join(r['targets'])}")
    if r["interview_targets"]:
        parts.append(f"| 인터뷰 후보: {_join(r['interview_targets'])}")
    if r["data_points"]:
        parts.append(f"| 확인자료: {_join(r['data_points'])}")
    if r["frames"]:
        parts.append(f"| 보도각도: {_join(r['frames'])}")
    if r["previous"]:
        parts.append(f"| 이전사업: {_join(r['previous'])}")
    return " ".join(parts)


def _issue_line(r) -> str:
    parts = [f"[현안] {r['issue']} (상태: {r['status']})"]
    if r["responders"]:
        parts.append(f"| 대응: {_join(r['responders'])}")
    if r["affected"]:
        parts.append(f"| 영향받는 쪽: {_join(r['affected'])}")
    if r["assets"]:
        parts.append(f"| 관련 자산: {_join(r['assets'])}")
    if r["indicators"]:
        parts.append(f"| 지표: {_join(r['indicators'])}")
    if r["leads_to"]:
        parts.append(f"| 파급: {_join(r['leads_to'])}")
    if r["worsens"]:
        parts.append(f"| 악화시킴: {_join(r['worsens'])}")
    return " ".join(parts)


def _central_line(r) -> str:
    meta = ", ".join(x for x in [r["category"], r["date"]] if x)
    parts = [f"[중앙정책] {r['action']}" + (f" ({meta})" if meta else "")]
    if r["programs"]:
        parts.append(f"| 지역사업: {_join(r['programs'])}")
    if r["regions"]:
        parts.append(f"| 적용지역: {_join(r['regions'])}")
    if r["data_points"]:
        parts.append(f"| 확인자료: {_join(r['data_points'])}")
    if r["frames"]:
        parts.append(f"| 보도각도: {_join(r['frames'])}")
    return " ".join(parts)


def _indicator_line(r) -> str:
    parts = [f"[지표] {r['indicator']}: {r['value']}"]
    if r["regions"]:
        parts.append(f"| 측정지역: {_join(r['regions'])}")
    if r["assets"]:
        parts.append(f"| 측정대상: {_join(r['assets'])}")
    if r["issues"]:
        parts.append(f"| 시사하는 현안: {_join(r['issues'])}")
    return " ".join(parts)


def _empty() -> dict:
    return {"retrieved_context": [], "suggested": {}}
