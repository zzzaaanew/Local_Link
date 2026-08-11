import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

AURA_URI = os.getenv("NEO4J_URI", "neo4j+s://d8a5f68a.databases.neo4j.io")
AURA_USER = os.getenv("NEO4J_USERNAME", "d8a5f68a")
AURA_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

driver = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASSWORD))

def check_db():
    with driver.session() as session:
        result = session.run("CALL db.labels()")
        labels = [record[0] for record in result]
        print("Labels in DB:", labels)
        
        for label in labels:
            res = session.run(f"MATCH (n:`{label}`) RETURN count(n) as cnt")
            print(f"{label}: {res.single()['cnt']}")

check_db()
driver.close()
