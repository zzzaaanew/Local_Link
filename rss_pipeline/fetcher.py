import feedparser
import requests
from newspaper import Article, Config
from datetime import datetime

# 신뢰할 수 있는 주요 언론사 RSS 피드 목록 (사회/지역/경제 중심)
DEFAULT_RSS_FEEDS = [
    "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=03&plink=RSSREADER", # SBS 사회
    "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02&plink=RSSREADER", # SBS 경제
    "http://imnews.imbc.com/rss/news/news_04.xml", # MBC 사회
    "http://imnews.imbc.com/rss/news/news_05.xml", # MBC 경제
    "https://fs.jtbc.co.kr/RSS/society.xml", # JTBC 사회
    "https://fs.jtbc.co.kr/RSS/economy.xml", # JTBC 경제
    "https://www.ytn.co.kr/rss/society.xml", # YTN 사회
    "https://www.ytn.co.kr/rss/economy.xml", # YTN 경제
    "https://rss.donga.com/society.xml", # 동아일보 사회
    "https://rss.donga.com/economy.xml", # 동아일보 경제
    "http://www.hani.co.kr/rss/society/", # 한겨레 사회
    "http://www.hani.co.kr/rss/economy/", # 한겨레 경제
]

# 안티 크롤링(403/404) 우회를 위한 헤더 설정
user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
config = Config()
config.browser_user_agent = user_agent
config.request_timeout = 10

def fetch_rss_feed(feed_url):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching RSS: {feed_url}")
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
        print(f"Failed to fetch {feed_url}: {e}")
        return []

def scrape_article_text(url):
    try:
        article = Article(url, config=config, language='ko')
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return ""

def get_articles_from_feeds(feeds=DEFAULT_RSS_FEEDS, max_per_feed=10):
    all_articles = []
    for feed in feeds:
        entries = fetch_rss_feed(feed)
        for entry in entries[:max_per_feed]:
            # 중복 체크 로직 (여기서는 단순 리스트 통과)
            all_articles.append(entry)
    
    return all_articles
