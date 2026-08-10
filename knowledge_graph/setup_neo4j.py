import os
import sys
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables (from .env or system environment)
load_dotenv()

AURA_URI = os.getenv("AURA_URI")
AURA_USER = os.getenv("AURA_USER")
AURA_PASSWORD = os.getenv("AURA_PASSWORD")

if not all([AURA_URI, AURA_USER, AURA_PASSWORD]):
    print("Error: Missing Neo4j credentials. Please set AURA_URI, AURA_USER, AURA_PASSWORD.")
    sys.exit(1)

def setup_constraints():
    driver = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASSWORD))
    
    with driver.session() as session:
        # 1. Drop the old ID index if it exists. 
        # Note: The index name 'basenode_id_index' might vary depending on how it was created.
        try:
            print("Dropping existing index on BaseNode(id)...")
            session.run("DROP INDEX basenode_id_index IF EXISTS")
        except Exception as e:
            print(f"Notice: {e}")

        # 2. Create the unique constraint on BaseNode(name)
        try:
            print("Creating unique constraint on BaseNode(name)...")
            session.run(
                "CREATE CONSTRAINT basenode_name_unique IF NOT EXISTS "
                "FOR (n:BaseNode) REQUIRE n.name IS UNIQUE"
            )
            print("Success! Unique constraint applied.")
        except Exception as e:
            print(f"Error creating constraint: {e}")

    driver.close()

if __name__ == "__main__":
    setup_constraints()
