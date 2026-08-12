import os
import logging
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

AURA_URI = os.getenv("NEO4J_URI", "neo4j+s://d8a5f68a.databases.neo4j.io")
AURA_USER = os.getenv("NEO4J_USERNAME", "d8a5f68a")
AURA_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

logger = logging.getLogger(__name__)

def is_url_processed(url):
    """Check if the URL has already been processed and saved in Neo4j."""
    if not AURA_PASSWORD:
        return False
    driver = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASSWORD))
    try:
        with driver.session() as session:
            result = session.run("MATCH (u:ProcessedArticle {url: $url}) RETURN u", url=url)
            return result.single() is not None
    except Exception as e:
        logger.error(f"Error checking URL in DB: {e}")
        return False
    finally:
        driver.close()

def mark_url_processed(url):
    """Mark the URL as processed in Neo4j."""
    if not AURA_PASSWORD:
        return
    driver = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASSWORD))
    try:
        with driver.session() as session:
            session.run("MERGE (u:ProcessedArticle {url: $url}) ON CREATE SET u.processed_at = datetime()", url=url)
    except Exception as e:
        logger.error(f"Error marking URL as processed: {e}")
    finally:
        driver.close()

def _safe_get_name(node):
    """Safely extract 'name' from a node dictionary, handling cases where the LLM returned a string instead of a dict."""
    if isinstance(node, dict):
        return node.get("name")
    elif isinstance(node, str):
        return node
    return None

def load_v2_to_neo4j(graph_data):
    if not graph_data or not AURA_PASSWORD:
        logger.warning("Graph data is empty or Neo4j credentials missing.")
        return

    driver = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASSWORD))
    try:
        with driver.session() as session:
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

            # LocalRegion
            for n in nodes.get("local_regions", []):
                name = _safe_get_name(n)
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

            # 엣지 적재
            for rel in relationships:
                if not isinstance(rel, dict):
                    continue
                rel_type = rel.get("type","").upper().replace(" ","_").replace("-","_")
                if not rel_type:
                    continue
                q = f"""
                MATCH (s:BaseNode {{name: $src}}), (t:BaseNode {{name: $tgt}})
                MERGE (s)-[r:{rel_type}]->(t)
                ON CREATE SET r.description=$desc
                """
                session.run(q, src=rel.get("source_name",""), tgt=rel.get("target_name",""), desc=rel.get("description",""))

    except Exception as e:
        logger.error(f"DB Load Error: {e}")
    finally:
        driver.close()
