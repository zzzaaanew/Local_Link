"""주간기획 발제 파이프라인 — 정부 주간일정 + 지식그래프 → 취재 계획서.

  Phase 1-A  업로드된 정부 주간일정 텍스트 로드   (weekly_schedule.py)
  Phase 1-B  LLM 1차 — 경북 연결 가능 일정 선별   (저비용 모델)
  Phase 2    Neo4j 지식그래프 팩트 수집          (graph.py, LLM 없음)
  Phase 3    LLM 2차 — 취재 계획서 최대 3건 생성

이전에는 경북일보 RSS(이미 보도된 기사)를 근거로 삼았으나, 이미 나온 기사가
반복 추천되는 문제가 있어 '아직 일어나지 않은 정부 일정'을 근거로 바꿨다.
목적은 다가올 발표를 미리 대비하는 예측형 발제다.
"""
import json
import logging
import os

import graph
import llm
import weekly_schedule
from collectors import today_context
from llm import merge_usage
from prompts.builder import load_prompt

logger = logging.getLogger(__name__)

FILTER_MODEL = os.environ.get("ANTHROPIC_FILTER_MODEL", "claude-haiku-4-5")
FILTER_MAX_TOKENS = 3000
PLAN_MAX_TOKENS = 8000
SCHEDULE_LIMIT = 15000  # 1차 호출에 넣을 일정 텍스트 상한


def run(count: int = 4, excluded_titles: list[str] | None = None) -> dict:
    """파이프라인 전체 실행. 반환: {"items": [...], "meta": {...}, "usage": {...}}"""
    today, day_of_week = today_context()

    # ── Phase 1-A: 내장된 정부 주간일정 ──────────────────
    schedule_text = weekly_schedule.load()

    # ── Phase 1-B: 경북 연결 가능 일정 선별 ──────────────
    filtered = _filter(schedule_text, today, day_of_week)

    # ── Phase 2: 지식그래프 ──────────────────────────────
    keywords = filtered.get("keywords") or ["경북", "산업", "고용", "인구"]
    ontology = graph.fetch_context(keywords)

    # ── Phase 3: 취재 계획서 ─────────────────────────────
    result = _generate(filtered, ontology, today, day_of_week, count, excluded_titles or [])

    # 두 번의 LLM 호출(선별 + 계획서) 토큰을 합쳐 사용량 기록에 넘긴다
    result["usage"] = merge_usage(filtered.pop("_usage", None), result.pop("_usage", None))
    result["meta"] = {
        "schedule_chars": len(schedule_text),
        "selected": len(filtered.get("government_schedule", [])),
        "keywords": keywords,
        "graph_facts": len(ontology.get("retrieved_context", [])),
        "graph_connected": graph.is_configured(),
        "date": today,
    }
    return result


# ------------------------------------------------------------
# Phase 1-B
# ------------------------------------------------------------

def _filter(schedule_text: str, today: str, day_of_week: str) -> dict:
    user_message = (
        f"오늘은 {today}({day_of_week})이다.\n"
        "다음 정부 주간일정에서 경북과 연결 가능한 일정을 선별해라.\n\n"
        f"[정부 주간일정]\n{schedule_text[:SCHEDULE_LIMIT]}"
    )
    try:
        parsed, usage = llm.generate_json(
            load_prompt("weekly_filter"),
            user_message,
            max_tokens=FILTER_MAX_TOKENS,
            model=FILTER_MODEL,
        )
    except Exception as exc:
        # 선별 실패해도 원문 일정으로 계획서 생성은 시도한다.
        logger.warning("Phase 1-B 실패, 기본 키워드로 진행: %s", exc)
        return {
            "government_schedule": [],
            "keywords": ["경북", "산업", "고용", "인구"],
            "phase1_summary": "일정 선별에 실패해 원문 일정으로 진행합니다.",
            "_raw_schedule": schedule_text,
            "_usage": None,
        }

    parsed["_raw_schedule"] = schedule_text
    parsed["_usage"] = usage
    logger.info(
        "Phase 1-B: 일정 %d건 선별, 키워드 %s",
        len(parsed.get("government_schedule", [])),
        parsed.get("keywords"),
    )
    return parsed


# ------------------------------------------------------------
# Phase 3
# ------------------------------------------------------------

def _generate(
    filtered: dict,
    ontology: dict,
    today: str,
    day_of_week: str,
    count: int,
    excluded_titles: list[str],
) -> dict:
    schedule = filtered.get("government_schedule", [])
    if schedule:
        schedule_block = "\n".join(
            f"- [{s.get('scheduled_at', '')}] {s.get('agency', '')} / {s.get('title', '')}"
            f" — {s.get('description', '')} (경북 연결: {s.get('relevance', '')})"
            for s in schedule
        )
    else:
        schedule_block = (filtered.get("_raw_schedule") or "")[:SCHEDULE_LIMIT]

    facts = ontology.get("retrieved_context") or []
    facts_block = "\n".join(facts) if facts else "조회된 지역 팩트 없음"

    parts = [
        f"[오늘의 기준 날짜]\n{today} ({day_of_week})",
        f"[이번 주 취재 맥락]\n{filtered.get('phase1_summary', '')}",
        f"[정부 주간 일정]\n{schedule_block}",
        f"[지역 팩트 DB (지식그래프)]\n{facts_block}",
    ]
    suggested = ontology.get("suggested") or {}
    if any(suggested.values()):
        parts.append(
            "[그래프가 제안하는 재료]\n" + json.dumps(suggested, ensure_ascii=False, indent=2)
        )
    if excluded_titles:
        listed = "\n".join(f"- {t}" for t in excluded_titles)
        parts.append(
            "[이미 제안한 아이템 — 같거나 유사한 각도는 제외하고 새로운 각도만 제안할 것]\n" + listed
        )
    parts.append(
        f"위 자료를 바탕으로 시스템 프롬프트 지시에 따라 취재 계획서를 최대 {count}건 생성하고, "
        "'# 출력 래핑' 절의 JSON 형식으로만 출력하라."
    )

    parsed, usage = llm.generate_json(
        load_prompt("weekly_plan"), "\n\n".join(parts), max_tokens=PLAN_MAX_TOKENS
    )
    items = parsed.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("취재 계획서를 생성하지 못했습니다.")

    return {"items": items[:count], "_usage": usage}
