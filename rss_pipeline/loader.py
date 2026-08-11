import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

AURA_URI = os.getenv("NEO4J_URI", "neo4j+s://d8a5f68a.databases.neo4j.io")
AURA_USER = os.getenv("NEO4J_USERNAME", "d8a5f68a")
AURA_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

def load_v2_to_neo4j(graph_data):
    if not graph_data or not AURA_PASSWORD:
        print("Graph data is empty or Neo4j credentials missing.")
        return

    driver = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASSWORD))
    try:
        with driver.session() as session:
            nodes = graph_data.get("nodes", {})
            relationships = graph_data.get("relationships", [])

            # 노드 적재 (BaseNode MERGE 후 특정 라벨 SET)
            for n in nodes.get("central_actions", []):
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.date=$date, x.category=$category ON MATCH SET x.date=$date, x.category=$category SET x:CentralAction", name=n["name"], date=n.get("date",""), category=n.get("category",""))

            for n in nodes.get("programs", []):
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.program_type=$program_type, x.status=$status ON MATCH SET x.program_type=$program_type, x.status=$status SET x:Program", name=n["name"], program_type=n.get("program_type",""), status=n.get("status",""))

            for n in nodes.get("local_regions", []):
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.level=$level ON MATCH SET x.level=$level SET x:LocalRegion", name=n["name"], level=n.get("level",""))

            for n in nodes.get("local_assets", []):
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.asset_type=$asset_type ON MATCH SET x.asset_type=$asset_type SET x:LocalAsset", name=n["name"], asset_type=n.get("asset_type",""))

            for n in nodes.get("stakeholders", []):
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.stakeholder_type=$stakeholder_type ON MATCH SET x.stakeholder_type=$stakeholder_type SET x:Stakeholder", name=n["name"], stakeholder_type=n.get("stakeholder_type",""))

            for n in nodes.get("local_issues", []):
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.status=$status ON MATCH SET x.status=$status SET x:LocalIssue", name=n["name"], status=n.get("status",""))

            for n in nodes.get("eco_indicators", []):
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.current_value=$current_value ON MATCH SET x.current_value=$current_value SET x:EcoIndicator", name=n["name"], current_value=n.get("current_value",""))

            for n in nodes.get("data_points", []):
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.data_type=$data_type ON MATCH SET x.data_type=$data_type SET x:DataPoint", name=n["name"], data_type=n.get("data_type",""))

            for n in nodes.get("reporting_frames", []):
                session.run("MERGE (x:BaseNode {name: $name}) ON CREATE SET x.priority=$priority ON MATCH SET x.priority=$priority SET x:ReportingFrame", name=n["name"], priority=n.get("priority",""))

            for n in nodes.get("national_issues", []):
                session.run("MERGE (x:BaseNode {name: $name}) SET x:NationalIssue", name=n["name"])

            # 엣지 적재
            for rel in relationships:
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
        print(f"DB Load Error: {e}")
    finally:
        driver.close()
