import time
import os
from fetcher import get_articles_from_feeds, scrape_article_text
from extractor import extract_knowledge_graph
from loader import load_v2_to_neo4j

def run_pipeline():
    print("Starting pipeline...")
    
    # 1. RSS 피드에서 최신 기사 수집 (목표: 100~150개)
    # 현재 6개 피드가 등록되어 있으므로 각 25개씩 수집 시 최대 150개
    articles = get_articles_from_feeds(max_per_feed=25)
    print(f"Total articles found: {len(articles)}")
    
    # 배치 설정
    BATCH_SIZE = 5
    SLEEP_SECONDS = 30 # LLM Rate Limit 방지용 대기 시간
    
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i:i+BATCH_SIZE]
        print(f"\nProcessing batch {i//BATCH_SIZE + 1}...")
        
        for article in batch:
            print(f"  Scraping: {article['title']}")
            text = scrape_article_text(article["link"])
            
            if not text:
                print("    -> No text scraped. Skipping.")
                continue
                
            print("  Extracting knowledge graph...")
            graph_json = extract_knowledge_graph(text)
            
            if graph_json:
                print("  Loading to Neo4j...")
                load_v2_to_neo4j(graph_json)
            else:
                print("    -> Extraction failed.")
                
        # 마지막 배치가 아니면 대기
        if i + BATCH_SIZE < len(articles):
            print(f"Waiting {SLEEP_SECONDS} seconds before next batch...")
            time.sleep(SLEEP_SECONDS)
            
    print("Pipeline finished.")

if __name__ == "__main__":
    run_pipeline()
