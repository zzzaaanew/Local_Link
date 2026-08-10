"""보도자료 발 발제 — 보도자료 + 지식그래프 → 발제 후보.

  1단계  LLM: 보도자료에서 엔티티(지역/기관/키워드) 추출   [저비용 모델]
  2단계  Neo4j: 추출한 키워드로 지역 맥락 팩트 수집        [LLM 없음]
  3단계  LLM: 보도자료 + 그래프 팩트 → 발제 후보 N건

데모(demo_pipeline_db.py) 대비 달라진 점
  · 엔티티 추출을 하드코딩 사전 → LLM으로 교체
    (데모는 '포항/복지' 등 고정 키워드라 다른 지역/주제에서 매칭되지 않았다)
  · Cypher는 기존 graph.py 재사용 — 파라미터 바인딩, 실제 스키마에 맞춘 쿼리
  · 첫 아이템 자동 선택 + 자동 초안 제거 — 발제는 사용자가 고르고,
    이후 취재→초안→저장은 기존 발제 흐름(/pitch, /selected)을 그대로 탄다
  · 접속 정보는 환경변수로만 읽는다 (데모는 소스에 평문 하드코딩)
"""
import json
import logging
import os

import graph
import llm
from prompts.builder import load_prompt

logger = logging.getLogger(__name__)

ENTITY_MODEL = os.environ.get("ANTHROPIC_FILTER_MODEL", "claude-haiku-4-5")
ENTITY_MAX_TOKENS = 1500
PITCH_MAX_TOKENS = 6000
MAX_SOURCE_CHARS = 8000


def generate(source_text: str, user_prompt: str | None = None, count: int = 3) -> dict:
    """보도자료로부터 발제 후보를 만든다.

    반환: {"pitches": [...], "meta": {...}}
    """
    text = (source_text or "").strip()[:MAX_SOURCE_CHARS]
    if len(text) < 50:
        raise ValueError("보도자료 본문이 너무 짧습니다.")

    entities, entity_usage = _extract_entities(text)
    keywords = _search_terms(entities)
    ontology = graph.fetch_context(keywords)

    items, pitch_usage = _generate_pitches(text, user_prompt, ontology, count)
    pitches = [_normalize(it, i) for i, it in enumerate(items[:count])]

    return {
        "pitches": pitches,
        "usage": llm.merge_usage(entity_usage, pitch_usage),
        "meta": {
            "entities": entities,
            "keywords": keywords,
            "graph_connected": graph.is_configured(),
            "graph_facts": len(ontology.get("retrieved_context", [])),
        },
    }


# ------------------------------------------------------------
# 1단계 — 엔티티 추출
# ------------------------------------------------------------

def _extract_entities(text: str) -> tuple[dict, dict | None]:
    """보도자료에서 지역·기관·이슈 키워드를 뽑는다. 실패해도 파이프라인은 계속된다.

    반환: (엔티티, usage) — usage 는 실패 시 None.
    """
    try:
        parsed, usage = llm.generate_json(
            load_prompt("press_entities"),
            f"[보도자료]\n{text}",
            max_tokens=ENTITY_MAX_TOKENS,
            model=ENTITY_MODEL,
        )
    except Exception as exc:
        logger.warning("엔티티 추출 실패, 그래프 조회 없이 진행: %s", exc)
        return {"regions": [], "stakeholders": [], "keywords": []}, None

    return {
        "regions": _str_list(parsed.get("regions")),
        "stakeholders": _str_list(parsed.get("stakeholders")),
        "keywords": _str_list(parsed.get("keywords")),
    }, usage


def _search_terms(entities: dict) -> list[str]:
    """그래프 조회용 키워드. 이슈 키워드를 앞에 두고 지역/기관을 뒤에 붙인다."""
    terms = list(entities.get("keywords") or [])
    for extra in (entities.get("regions") or []) + (entities.get("stakeholders") or []):
        if extra not in terms:
            terms.append(extra)
    return terms[:8]


# ------------------------------------------------------------
# 3단계 — 발제 후보 생성
# ------------------------------------------------------------

def _generate_pitches(
    text: str, user_prompt: str | None, ontology: dict, count: int
) -> tuple[list[dict], dict]:
    payload = {
        "ontology_context": ontology,
        "requested_count": count,
    }
    parts = [f"보도자료를 읽고 발제 후보를 정확히 {count}건 제안하라."]
    if user_prompt and user_prompt.strip():
        parts.append(f"[기자의 요청사항 — 최우선 반영]\n{user_prompt.strip()}")
    parts.append(f"[보도자료 원문]\n{text}")
    parts.append(
        "[지식그래프 맥락]\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    parts.append("지정된 JSON 객체만 출력한다.")

    parsed, usage = llm.generate_json(
        load_prompt("press_pitch"), "\n\n".join(parts), max_tokens=PITCH_MAX_TOKENS
    )
    items = parsed.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("발제 후보를 생성하지 못했습니다.")
    return items, usage


# ------------------------------------------------------------
# 정규화 (프론트 발제 카드 계약)
# ------------------------------------------------------------

_ALIASES = {
    "title": ("title", "headline"),
    "summary": ("summary", "story_angle", "angle"),
    "why": ("why", "why_now", "reason"),
    "source_basis": ("source_basis", "basis", "evidence"),
    "tag": ("tag", "category", "layer"),
}


def _normalize(item: dict, index: int) -> dict:
    local = item.get("local_connection") or {}
    return {
        "id": f"press-{index + 1}",
        "org": _pick(item, "org") or _first(local.get("stakeholders")),
        "region": _pick(item, "region") or _first(local.get("regions")),
        "tag": _pick(item, "tag"),
        "title": _pick(item, "title") or "(제목 없음)",
        "summary": _pick(item, "summary"),
        "why": _pick(item, "why"),
        "source_basis": _pick(item, "source_basis"),
        "questions": _as_list(item, "questions", "key_questions"),
        "interview_targets": _as_list(item, "interview_targets", "sources"),
        "data_to_check": _as_list(item, "data_to_check", "data_needed"),
    }
    # 프롬프트가 draft_article(예상 초안)을 만들더라도 화면으로 넘기지 않는다.
    # 취재 전에 쓴 초안은 근거가 없어 할루시네이션 위험이 크다. 초안은 기자가
    # 취재 내용을 입력한 뒤 데스크에서 생성한다(desk.add_research_and_draft).



def _pick(item: dict, field: str) -> str:
    for key in _ALIASES.get(field, (field,)):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _as_list(item: dict, *keys) -> list[str]:
    """리스트 필드를 문자열 배열로. {target, reason} 형태도 받아들인다."""
    for key in keys:
        value = item.get(key)
        if not isinstance(value, list) or not value:
            continue
        out = []
        for v in value:
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
            elif isinstance(v, dict):
                label = v.get("target") or v.get("name") or v.get("title") or ""
                reason = v.get("reason") or v.get("why") or ""
                if label:
                    out.append(f"{label} — {reason}" if reason else label)
        if out:
            return out
    return []


def _str_list(value) -> list[str]:
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def _first(value) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value) if isinstance(value, str) else ""
