import os
import logging
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# 환경변수 (AURA_* 및 NEO4J_* 호환)
AURA_URI = os.getenv("AURA_URI") or os.getenv("NEO4J_URI", "neo4j+s://d8a5f68a.databases.neo4j.io")
AURA_USER = os.getenv("AURA_USER") or os.getenv("NEO4J_USERNAME", "d8a5f68a")
AURA_PASSWORD = os.getenv("AURA_PASSWORD") or os.getenv("NEO4J_PASSWORD", "")

logger = logging.getLogger(__name__)

# LLM 생성 관계 타입 화이트리스트 (Cypher Injection 방어)
ALLOWED_RELATIONSHIPS = {
    "OPERATES", "RESPONDS_TO", "LOCATED_IN", "HAS_ISSUE", "INVOLVES",
    "AFFECTED_BY", "MEASURES", "INDICATES", "REQUIRES_CHECK", "SUGGESTS_FRAME",
    "HAS_INTERVIEW_TARGET", "LOCALIZED_TO", "TARGETS", "CONTRIBUTES_TO",
    "WORSENS", "HAS_PREVIOUS_PROGRAM", "CONFLICTS_WITH",
}

# 지역명 표준화 매핑 딕셔너리
REGION_NORM_MAP = {
    # 광역/도
    "경상북도": "경북",
    "경북도": "경북",
    "대구경북": "대구·경북",
    "대구 경북": "대구·경북",
    "경상남도": "경남",
    "경남도": "경남",
    "서울특별시": "서울",
    "서울시": "서울",
    "대구광역시": "대구",
    "대구시": "대구",
    "부산광역시": "부산",
    "부산시": "부산",
    "인천광역시": "인천",
    "인천시": "인천",
    "광주광역시": "광주",
    "광주시": "광주",
    "대전광역시": "대전",
    "대전시": "대전",
    "울산광역시": "울산",
    "울산시": "울산",
    "세종특별자치시": "세종",
    "세종시": "세종",
    "경기도": "경기",
    "강원도": "강원",
    "강원특별자치도": "강원",
    "충청북도": "충북",
    "충북도": "충북",
    "충청남도": "충남",
    "충남도": "충남",
    "전라북도": "전북",
    "전북도": "전북",
    "전북특별자치도": "전북",
    "전라남도": "전남",
    "전남도": "전남",
    "제주도": "제주",
    "제주특별자치도": "제주",
    
    # 기초지자체 (경북/대구)
    "포항": "포항시",
    "경주": "경주시",
    "김천": "김천시",
    "안동": "안동시",
    "구미": "구미시",
    "영주": "영주시",
    "영천": "영천시",
    "상주": "상주시",
    "문경": "문경시",
    "경산": "경산시",
    "군위": "군위군",
    "의성": "의성군",
    "청송": "청송군",
    "영양": "영양군",
    "영덕": "영덕군",
    "청도": "청도군",
    "고령": "고령군",
    "성주": "성주군",
    "칠곡": "칠곡군",
    "예천": "예천군",
    "봉화": "봉화군",
    "울진": "울진군",
    "울릉": "울릉군",
    
    # 경기/기타 주요 도시
    "경기도 광주": "경기 광주시",
    "경기도 광주시": "경기 광주시",
    "경기 광주": "경기 광주시",
    "경기도 남양주": "남양주시",
    "경기도 남양주시": "남양주시",
    "경기 남양주": "남양주시",
    "경기 성남시": "성남시",
    "경기 파주시": "파주시",
    "경기 부천시": "부천시",
    "경기 화성특례시": "화성시",
    "경기 과천": "과천시",
    "경기 과천시": "과천시",
    "과천": "과천시",
    "군포": "군포시",
    "경남 통영시": "통영시",
}

logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)

_driver = None

def _is_configured() -> bool:
    return bool(AURA_URI and AURA_USER and AURA_PASSWORD)

def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASSWORD))
    return _driver

def close():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None

def filter_new_urls(urls):
    """아직 처리하지 않은 URL만 남긴다 (일괄 쿼리)"""
    urls = [u for u in (urls or []) if u]
    if not _is_configured() or not urls:
        return urls
    try:
        with _get_driver().session() as session:
            done = {
                r["url"]
                for r in session.run(
                    "MATCH (u:ProcessedArticle) WHERE u.url IN $urls RETURN u.url AS url",
                    urls=urls,
                )
            }
    except Exception as e:
        logger.error(f"Error checking processed URLs: {e}")
        return urls
    if done:
        logger.info(f"Already processed: {len(done)} of {len(urls)}")
    return [u for u in urls if u not in done]

def is_url_processed(url):
    if not _is_configured():
        return False
    try:
        with _get_driver().session() as session:
            result = session.run("MATCH (u:ProcessedArticle {url: $url}) RETURN u", url=url)
            return result.single() is not None
    except Exception as e:
        logger.error(f"Error checking URL in DB: {e}")
        return False

def mark_url_processed(url):
    if not _is_configured():
        return
    try:
        with _get_driver().session() as session:
            session.run("MERGE (u:ProcessedArticle {url: $url}) ON CREATE SET u.processed_at = datetime()", url=url)
    except Exception as e:
        logger.error(f"Error marking URL as processed: {e}")

def _normalize_name(name):
    if not name or not isinstance(name, str):
        return name
    name_clean = name.strip()
    return REGION_NORM_MAP.get(name_clean, name_clean)

def _safe_get_name(node):
    if isinstance(node, dict):
        return node.get("name")
    elif isinstance(node, str):
        return node
    return None

def load_v2_to_neo4j(graph_data):
    if not graph_data or not _is_configured():
        logger.warning("Graph data is empty or Neo4j credentials missing.")
        return

    try:
        with _get_driver().session() as session:
            nodes = graph_data.get("nodes", {})
            relationships = graph_data.get("relationships", [])

            # CentralAction
            for n in nodes.get("central_actions", []):
                name = _safe_get_name(n)
                if not name: continue
                category = n.get("category", "") if isinstance(n, dict) else ""
                date = n.get("date", "") if isinstance(n, dict) else ""
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.date=$date, x.category=$category ON MATCH SET x.date=$date, x.category=$category SET x:CentralAction", name=name, date=date, category=category)

            # Program
            for n in nodes.get("programs", []):
                name = _safe_get_name(n)
                if not name: continue
                program_type = n.get("program_type", "") if isinstance(n, dict) else ""
                status = n.get("status", "") if isinstance(n, dict) else ""
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.program_type=$program_type, x.status=$status ON MATCH SET x.program_type=$program_type, x.status=$status SET x:Program", name=name, program_type=program_type, status=status)

            # LocalRegion (실시간 정규화)
            for n in nodes.get("local_regions", []):
                name = _normalize_name(_safe_get_name(n))
                if not name: continue
                level = n.get("level", "") if isinstance(n, dict) else ""
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.level=$level ON MATCH SET x.level=$level SET x:LocalRegion", name=name, level=level)

            # LocalAsset
            for n in nodes.get("local_assets", []):
                name = _safe_get_name(n)
                if not name: continue
                asset_type = n.get("asset_type", "") if isinstance(n, dict) else ""
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.asset_type=$asset_type ON MATCH SET x.asset_type=$asset_type SET x:LocalAsset", name=name, asset_type=asset_type)

            # Stakeholder
            for n in nodes.get("stakeholders", []):
                name = _safe_get_name(n)
                if not name: continue
                stakeholder_type = n.get("stakeholder_type", "") if isinstance(n, dict) else ""
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.stakeholder_type=$stakeholder_type ON MATCH SET x.stakeholder_type=$stakeholder_type SET x:Stakeholder", name=name, stakeholder_type=stakeholder_type)

            # LocalIssue
            for n in nodes.get("local_issues", []):
                name = _safe_get_name(n)
                if not name: continue
                status = n.get("status", "") if isinstance(n, dict) else ""
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.status=$status ON MATCH SET x.status=$status SET x:LocalIssue", name=name, status=status)

            # EcoIndicator
            for n in nodes.get("eco_indicators", []):
                name = _safe_get_name(n)
                if not name: continue
                current_value = n.get("current_value", "") if isinstance(n, dict) else ""
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.current_value=$current_value ON MATCH SET x.current_value=$current_value SET x:EcoIndicator", name=name, current_value=current_value)

            # DataPoint
            for n in nodes.get("data_points", []):
                name = _safe_get_name(n)
                if not name: continue
                data_type = n.get("data_type", "") if isinstance(n, dict) else ""
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.data_type=$data_type ON MATCH SET x.data_type=$data_type SET x:DataPoint", name=name, data_type=data_type)

            # ReportingFrame
            for n in nodes.get("reporting_frames", []):
                name = _safe_get_name(n)
                if not name: continue
                priority = n.get("priority", "") if isinstance(n, dict) else ""
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.priority=$priority ON MATCH SET x.priority=$priority SET x:ReportingFrame", name=name, priority=priority)

            # NationalIssue
            for n in nodes.get("national_issues", []):
                name = _safe_get_name(n)
                if not name: continue
                session.run("MERGE (x:BaseNode {name: $name}) SET x:NationalIssue", name=name)

            # 엣지 적재 (정규화된 src, tgt 매핑 + 화이트리스트)
            for rel in relationships:
                if not isinstance(rel, dict):
                    continue
                rel_type = rel.get("type","").upper().replace(" ","_").replace("-","_")
                if not rel_type:
                    continue
                if rel_type not in ALLOWED_RELATIONSHIPS:
                    logger.warning("허용되지 않은 관계 타입 무시: %s", rel_type)
                    continue
                src = _normalize_name(rel.get("source_name",""))
                tgt = _normalize_name(rel.get("target_name",""))
                q = f"""
                MATCH (s:BaseNode {{name: $src}}), (t:BaseNode {{name: $tgt}})
                MERGE (s)-[r:{rel_type}]->(t)
                ON CREATE SET r.description=$desc
                """
                session.run(q, src=src, tgt=tgt, desc=rel.get("description",""))

    except Exception as e:
        logger.error(f"DB Load Error: {e}")
