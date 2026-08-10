"""RSS 수집 — 리라이팅 후보(통신사 기사) 발굴용.

RSS는 언론사가 배포를 목적으로 공개한 피드이므로 크롤링보다 안전하고 안정적이다.
추후 매체를 늘리려면 WIRE_FEEDS에 추가하기만 하면 된다.

참고: 주간기획 발제(오늘의 발제 추천)는 예전에 경북일보 RSS를 근거로 삼았으나
'이미 보도된 기사'가 반복 추천되는 문제로 정부 주간일정 기반으로 전면 교체했다
(weekly_schedule.py + source_pipeline.py). 그래서 지역 매체 피드 수집 코드는 제거했다.
"""
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

TIMEOUT = 15.0
MAX_ITEMS_PER_FEED = 30
SUMMARY_CHARS = 400

# 리라이팅 후보용 — 통신사(연합뉴스) 섹션 피드.
# 'local'(지역) 섹션은 제외한다. 이미 지역 뉴스라 리라이팅 대상이 아니다.
# 연예/스포츠도 제외한다(지역 확장성 없음).
WIRE_FEEDS: list[tuple[str, str]] = [
    ("연합뉴스", "https://www.yna.co.kr/rss/news.xml"),
    ("연합뉴스", "https://www.yna.co.kr/rss/society.xml"),
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("연합뉴스", "https://www.yna.co.kr/rss/industry.xml"),
    ("연합뉴스", "https://www.yna.co.kr/rss/politics.xml"),
    ("연합뉴스", "https://www.yna.co.kr/rss/health.xml"),
]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _fetch_feed(name: str, url: str) -> list[dict]:
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            res = client.get(url, headers={"User-Agent": _UA})
        res.raise_for_status()
    except Exception as exc:
        logger.warning("RSS 요청 실패 [%s]: %s", name, exc)
        return []

    feed = feedparser.parse(res.content)
    items = []
    for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
        summary = entry.get("summary") or entry.get("description") or ""
        items.append(
            {
                "source": name,
                "title": (entry.get("title") or "").strip(),
                "summary": _clean(summary)[:SUMMARY_CHARS],
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "author": entry.get("author", ""),
            }
        )
    logger.info("RSS 수집 완료 [%s]: %d건", name, len(items))
    return items


def collect_wire_articles(hours: int = 24) -> list[dict]:
    """통신사 RSS에서 최근 기사만 모아 중복 제거 후 반환한다.

    프롬프트의 '당일 발행' 요건을 pubDate로 직접 판정하므로 LLM이 날짜를
    추측할 필요가 없다. 반환 항목의 url/published_at은 피드 원본 값이다.
    """
    seen: set[str] = set()
    out: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    for name, url in WIRE_FEEDS:
        for item in _fetch_feed(name, url):
            link = item.get("link") or ""
            if not link or link in seen:
                continue
            published = _parse_published(item.get("published"))
            if published and published < cutoff:
                continue  # 오래된 기사 제외
            seen.add(link)
            item["published_at"] = (
                published.astimezone(KST).strftime("%Y-%m-%d %H:%M") if published else ""
            )
            out.append(item)

    out.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    logger.info("통신사 기사 수집: %d건 (최근 %d시간)", len(out), hours)
    return out


def _parse_published(value: str | None) -> datetime | None:
    """RSS pubDate 파싱. 실패하면 None (필터에서 걸러내지 않고 통과시킨다)."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(timezone.utc)


def _clean(text: str) -> str:
    """RSS 요약에 섞인 태그·공백을 정리한다."""
    import re

    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def today_context() -> tuple[str, str]:
    """오늘 날짜와 요일 (프롬프트에 주입)."""
    now = datetime.now()
    days = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    return now.strftime("%Y-%m-%d"), days[now.weekday()]
