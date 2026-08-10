"""리라이팅 기사 후보 — 통신사 당일 기사 중 지역 관점으로 다시 쓸 만한 것 선별.

  1단계  연합뉴스 RSS에서 최근 24시간 기사 수집   (collectors.py)
  2단계  LLM이 그 목록에서 경북 관점 리라이팅 후보를 선별

URL·발행일시·언론사명은 RSS 원본 값을 그대로 쓴다. LLM이 만들어낸 값은 신뢰하지
않고 수집 목록과 대조해 덮어쓴다 — 잘못된 링크를 기자에게 주지 않기 위함이다.
"""
import logging

import collectors
import llm
from prompts.builder import load_prompt

logger = logging.getLogger(__name__)

CANDIDATE_LIMIT = 120  # LLM에 넘길 후보 상한 (토큰 통제)
MAX_TOKENS = 6000
SUMMARY_CHARS = 180


def list_rewrite_targets(
    access_code_id: str, count: int = 4, excluded_urls: list[str] | None = None
) -> dict:
    """리라이팅 기사 후보 목록.

    excluded_urls: '새로고침'에서 이전에 받은 URL. 겹치지 않는 후보를 만든다.
    """
    excluded = set(excluded_urls or [])
    articles = [a for a in collectors.collect_wire_articles(hours=24) if a["link"] not in excluded]
    if not articles:
        raise RuntimeError("통신사 기사를 수집하지 못했습니다. RSS 상태를 확인하세요.")

    pool = articles[:CANDIDATE_LIMIT]
    parsed, usage = llm.generate_json(
        load_prompt("rewrite_targets"), _build_message(pool, count), max_tokens=MAX_TOKENS
    )

    items = parsed.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("리라이팅 후보를 생성하지 못했습니다.")

    targets = [t for t in (_normalize(it, pool, i) for i, it in enumerate(items[:count])) if t]
    return {"targets": targets, "collected": len(articles), "usage": usage}


def _build_message(pool: list[dict], count: int) -> str:
    lines = [
        f"아래는 연합뉴스에서 수집한 최근 24시간 기사 목록이다. "
        f"이 중에서 경북 관점 리라이팅 후보 {count}건을 선별하라.",
        "",
        "[기사 목록]",
    ]
    for i, a in enumerate(pool):
        lines.append(
            f"{i}. [{a.get('published_at', '')}] {a.get('title', '')}\n"
            f"   요약: {(a.get('summary') or '')[:SUMMARY_CHARS]}\n"
            f"   출처: {a.get('source', '')} | URL: {a.get('link', '')}"
        )
    lines.append("")
    lines.append("지정된 JSON 객체만 출력한다.")
    return "\n".join(lines)


def _normalize(item: dict, pool: list[dict], fallback_index: int) -> dict | None:
    """LLM 출력을 정리한다. URL 등 사실 필드는 수집 목록 원본으로 덮어쓴다."""
    source_article = _match_article(item, pool)
    if source_article is None:
        # 목록에 없는 기사를 지어낸 경우 — 버린다(잘못된 URL 노출 방지)
        logger.warning("수집 목록에 없는 후보를 버림: %.60s", item.get("title", ""))
        return None

    return {
        "id": f"rw-{fallback_index + 1}",
        "title": source_article.get("title", ""),
        "source": source_article.get("source", ""),
        "url": source_article.get("link", ""),
        "published_at": source_article.get("published_at", ""),
        "summary": _text(item, "summary"),
        "local_angle": _text(item, "local_angle", "angle"),
        "local_data_available": bool(item.get("local_data_available")),
        "priority_score": _score(item.get("priority_score")),
        "reason": _text(item, "reason", "why"),
    }


def _match_article(item: dict, pool: list[dict]) -> dict | None:
    """LLM이 고른 항목을 수집 목록과 대조한다. index → url → 제목 순으로 찾는다."""
    index = item.get("index")
    if isinstance(index, int) and 0 <= index < len(pool):
        return pool[index]

    url = (item.get("url") or "").strip()
    if url:
        for a in pool:
            if a.get("link") == url:
                return a

    title = (item.get("title") or "").strip()
    if title:
        for a in pool:
            if a.get("title", "").strip() == title:
                return a
    return None


def _text(item: dict, *keys) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _score(value) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 3
