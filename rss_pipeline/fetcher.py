import feedparser
import requests
import logging
from newspaper import Article, Config
from datetime import datetime

logger = logging.getLogger(__name__)

# 신뢰할 수 있는 주요 언론사 RSS 피드 목록 (지역 언론사 80% + 중앙 언론사 20%)
DEFAULT_RSS_FEEDS = [
    # 1. 경북매일 (지역/대구경북)
    "https://www.kyongbuk.co.kr/rss/S1N1.xml", # 종합
    "https://www.kyongbuk.co.kr/rss/S1N4.xml", # 사회
    "https://www.kyongbuk.co.kr/rss/S1N5.xml", # 경제
    
    # 2. 매일신문 (지역/대구경북)
    "https://www.imaeil.com/rss?cate=economy", # 경제
    "https://www.imaeil.com/rss?cate=society", # 사회
    
    # 3. 대구일보 (지역/대구경북)
    "https://www.idaegu.co.kr/rss/S1N2.xml", # 사회
    "https://www.idaegu.co.kr/rss/S1N3.xml", # 정치·행정
    
    # 4. 중앙 언론사 (약 20% - 상위 정책/거시 트렌드 연결용)
    "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=03&plink=RSSREADER", # SBS 사회
    "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02&plink=RSSREADER", # SBS 경제
]

# 안티 크롤링(403/404) 우회를 위한 헤더 설정
user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
config = Config()
config.browser_user_agent = user_agent
config.request_timeout = 10

def fetch_rss_feed(feed_url):
    logger.info(f"Fetching RSS: {feed_url}")
    try:
        headers = {'User-Agent': user_agent}
        response = requests.get(feed_url, headers=headers, timeout=10)
        parsed = feedparser.parse(response.content)
        articles = []
        for entry in parsed.entries:
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.get("published", ""),
            })
        return articles
    except Exception as e:
        logger.error(f"Failed to fetch {feed_url}: {e}")
        return []

def scrape_article_text(url):
    try:
        article = Article(url, config=config, language='ko')
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return ""

def get_articles_from_feeds(feeds=DEFAULT_RSS_FEEDS, max_per_feed=10):
    all_articles = []
    for feed in feeds:
        entries = fetch_rss_feed(feed)
        for entry in entries[:max_per_feed]:
            all_articles.append(entry)
    
    return all_articles
