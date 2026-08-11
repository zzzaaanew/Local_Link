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
        # Check total nodes
        result = session.run("MATCH (n:BaseNode) RETURN count(n) as count")
        print(f"Total BaseNodes: {result.single()['count']}")
        
        # Check recent SBS articles or any nodes added just now
        # SBS articles often don't have a specific region, or maybe they connected to "서울"
        # Let's just list 5 random relationships
        print("\nSample Relationships:")
        result = session.run("MATCH (a:BaseNode)-[r]->(b:BaseNode) RETURN a.name, type(r), b.name LIMIT 5")
        for record in result:
            print(f"({record['a.name']}) -[{record['type(r)']}]-> ({record['b.name']})")
            
        print("\nNodes loaded from RSS Pipeline today:")
        result = session.run("MATCH (n:BaseNode) RETURN n.name, labels(n) LIMIT 10")
        for record in result:
            print(f"{record['n.name']} : {record['labels(n)']}")

check_db()
driver.close()
