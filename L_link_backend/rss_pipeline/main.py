import time
import os
import logging
from fetcher import get_articles_from_feeds, scrape_article_text
from extractor import extract_knowledge_graph
from loader import load_v2_to_neo4j, is_url_processed, mark_url_processed

# 루트 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

def run_pipeline():
    logger.info("Starting RSS pipeline...")
    
    # 1. RSS 피드에서 최신 기사 수집 (목표: 100~150개)
    # 현재 6개 피드가 등록되어 있으므로 각 25개씩 수집 시 최대 150개
    articles = get_articles_from_feeds(max_per_feed=25)
    logger.info(f"Total articles found from feeds: {len(articles)}")
    
    # 중복되지 않은 새 기사만 필터링
    new_articles = []
    for article in articles:
        if not is_url_processed(article["link"]):
            new_articles.append(article)
            
    logger.info(f"New articles to process after duplicate check: {len(new_articles)}")
    if not new_articles:
        logger.info("No new articles to process. Pipeline finished.")
        return
    
    # 배치 설정
    BATCH_SIZE = 5
    SLEEP_SECONDS = 30 # LLM Rate Limit 방지용 대기 시간
    
    for i in range(0, len(new_articles), BATCH_SIZE):
        batch = new_articles[i:i+BATCH_SIZE]
        logger.info(f"Processing batch {i//BATCH_SIZE + 1}...")
        
        for article in batch:
            logger.info(f"  Scraping: {article['title']}")
            text = scrape_article_text(article["link"])
            
            if not text:
                logger.warning(f"    -> No text scraped for URL: {article['link']}. Skipping.")
                continue
                
            logger.info("  Extracting knowledge graph...")
            graph_json = extract_knowledge_graph(text)
            
            if graph_json:
                logger.info("  Loading to Neo4j...")
                load_v2_to_neo4j(graph_json)
                mark_url_processed(article["link"])
                logger.info("    -> Success.")
            else:
                logger.error(f"    -> Extraction failed for URL: {article['link']}")
                
        # 마지막 배치가 아니면 대기
        if i + BATCH_SIZE < len(new_articles):
            logger.info(f"Waiting {SLEEP_SECONDS} seconds before next batch...")
            time.sleep(SLEEP_SECONDS)
            
    logger.info("Pipeline finished.")

if __name__ == "__main__":
    run_pipeline()
