import os
import sys
import logging
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

AURA_URI = os.getenv("AURA_URI")
AURA_USER = os.getenv("AURA_USER")
AURA_PASSWORD = os.getenv("AURA_PASSWORD")

if not all([AURA_URI, AURA_USER, AURA_PASSWORD]):
    logger.error("Missing Neo4j credentials.")
    sys.exit(1)

driver = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASSWORD))

# Define allowed relationships for safety
ALLOWED_RELATIONSHIPS = {
    "INVOLVES", "TARGETS", "HAS_INTERVIEW_TARGET", "REQUIRES_CHECK", 
    "SUGGESTS_FRAME", "LOCATED_IN", "RESPONDS_TO", "AFFECTED_BY", 
    "HAS_ISSUE", "INDICATES", "CONTRIBUTES_TO", "WORSENS", "OPERATES",
    "HAS_PREVIOUS_PROGRAM", "MEASURES", "CONFLICTS_WITH"
}

def ingest_ontology(nodes_data: dict, relationships: list):
    """
    Ingests LLM-extracted ontology data into Neo4j using purely 'name' as the identifier.
    No temporary IDs are used or needed.
    """
    with driver.session() as session:
        # --- 1. Nodes Ingestion ---
        
        # Example: Stakeholders
        if nodes_data.get("stakeholders"):
            for item in nodes_data["stakeholders"]:
                # id 필드 사용 안 함, name만 사용
                session.run("""
                MERGE (n:Stakeholder {name: $name})
                ON CREATE SET n.stakeholder_type = $type
                ON MATCH SET n.stakeholder_type = coalesce($type, n.stakeholder_type)
                SET n:BaseNode
                """, name=item["name"], type=item.get("stakeholder_type", ""))
                
        # Example: Programs
        if nodes_data.get("programs"):
            for item in nodes_data["programs"]:
                session.run("""
                MERGE (n:Program {name: $name})
                ON CREATE SET n.program_type = $type, n.status = $status
                ON MATCH SET n.program_type = coalesce($type, n.program_type), n.status = coalesce($status, n.status)
                SET n:BaseNode
                """, name=item["name"], type=item.get("program_type", ""), status=item.get("status", ""))
                
        # (기타 LocalIssue, CentralAction 등의 노드 타입도 동일한 패턴으로 name만 사용하여 추가)
        
        # --- 2. Relationships Ingestion ---
        for rel in relationships:
            rel_type = rel.get("type", "").upper()
            if rel_type in ALLOWED_RELATIONSHIPS:
                # 1회용 ID가 아닌 실제 노드 이름(name)을 바로 사용
                source_name = rel.get("source_name")
                target_name = rel.get("target_name")
                
                if source_name and target_name:
                    rel_query = f"""
                    MATCH (s:BaseNode {{name: $source_name}}), (t:BaseNode {{name: $target_name}})
                    MERGE (s)-[r:{rel_type}]->(t)
                    ON CREATE SET r.description = $description
                    """
                    result = session.run(
                        rel_query, 
                        source_name=source_name, 
                        target_name=target_name, 
                        description=rel.get("description", "")
                    )
                    
                    # 💡 체크포인트: 실제로 엣지가 생성되었는지 확인하고 로깅하기
                    counters = result.consume().counters
                    if counters.relationships_created == 0:
                        logger.warning(f"⚠️ 엣지 생성 실패 (오타 의심 또는 이미 존재): {source_name} -> {target_name} ({rel_type})")

    print("Successfully ingested ontology using entirely Name-based logic (No IDs).")

# Example usage (for testing)
if __name__ == "__main__":
    # Dummy data representing LLM output (ID 필드 완전 제거, source_name/target_name 사용)
    sample_nodes = {
        "stakeholders": [
            {"name": "포항시청", "stakeholder_type": "지자체"},
            {"name": "지역상인회", "stakeholder_type": "시민단체"}
        ],
        "programs": [
            {"name": "포항사랑상품권", "program_type": "경제정책", "status": "진행중"}
        ]
    }
    sample_rels = [
        {"source_name": "포항사랑상품권", "target_name": "포항시청", "type": "INVOLVES", "description": "주관 기관"},
        {"source_name": "포항사랑상품권", "target_name": "지역상인회", "type": "TARGETS", "description": "주요 수혜자"}
    ]
    
    ingest_ontology(sample_nodes, sample_rels)
    driver.close()
