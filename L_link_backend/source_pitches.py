"""주간기획 발제 — 홈 '이번 주 기획 발제' 카드.

실제 생성은 source_pipeline(주간일정 → 선별 → 지식그래프 → 계획서)이 담당하고,
이 모듈은 그 결과를 프론트 카드 계약에 맞게 정규화하는 얇은 층이다.

프론트 계약:
  id, title, agency, region, timing, scheduled_at, why, summary, plan_markdown
  (plan_markdown 이 취재 계획서 전문 — 상세 화면에서 렌더링한다)
"""
import logging

import source_pipeline

logger = logging.getLogger(__name__)

_ALIASES = {
    "title": ("title", "headline"),
    "summary": ("summary", "story_angle", "angle"),
    "why": ("why", "why_now", "reason"),
    "agency": ("agency", "org", "publisher"),
    "region": ("region",),
    "timing": ("timing", "type"),
    "scheduled_at": ("scheduled_at", "published_at", "date"),
}


def weekly_plans(count: int = 3, excluded_titles: list[str] | None = None) -> dict:
    """이번 주 기획 발제.

    excluded_titles: '새로고침'에서 이전과 겹치지 않게 하려고 넘기는 제목 목록.
    """
    result = source_pipeline.run(count=count, excluded_titles=excluded_titles)
    items = [_normalize(it, i) for i, it in enumerate(result.get("items", []))]
    return {
        "pitches": items,
        "meta": result.get("meta", {}),
        "usage": result.get("usage"),
    }


def _normalize(item: dict, index: int) -> dict:
    return {
        "id": f"wk-{index + 1}",
        "title": _pick(item, "title") or "(제목 없음)",
        "agency": _pick(item, "agency"),
        "region": _pick(item, "region") or "경북",
        "timing": _pick(item, "timing"),
        "scheduled_at": _pick(item, "scheduled_at"),
        "why": _pick(item, "why"),
        "summary": _pick(item, "summary"),
        "plan_markdown": _plan(item),
    }


def _pick(item: dict, field: str) -> str:
    for key in _ALIASES.get(field, (field,)):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _plan(item: dict) -> str:
    """계획서 전문. 문자열이 아니라 섹션 dict로 와도 마크다운으로 조립한다."""
    value = item.get("plan_markdown") or item.get("plan") or item.get("markdown")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        return "\n\n".join(
            f"## {k}\n{v}" for k, v in value.items() if isinstance(v, str) and v.strip()
        )
    return ""
