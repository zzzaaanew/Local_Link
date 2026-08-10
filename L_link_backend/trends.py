"""홈 우측 레일 — 검색어 트렌드 (네이버 API Hub / Search Trend).

Search Trend API는 '인기 검색어 목록'을 제공하지 않고, 넘겨준 키워드의 상대
지수만 돌려준다. 그래서 지역 언론 관점의 후보 키워드 풀을 넓게 조회한 뒤
실제 검색지수 상위 몇 개만 골라 보여준다. 어떤 키워드가 뜨는지는 데이터에
따라 매주 달라진다.

후보 풀은 TREND_KEYWORDS 환경변수(쉼표 구분)로 교체할 수 있다.
샘플 폴백은 두지 않는다 — 실패는 502로 올려 원인을 그대로 보여준다.

반환 계약: {"keywords": [{keyword, change_pct, score}], "period": str}
"""
import logging
import os
import time

from fastapi import HTTPException

import naver

logger = logging.getLogger(__name__)

# 지역 언론이 관심 갖는 후보 풀. 이 중 검색지수 상위 TOP_N개가 화면에 뜬다.
# 첫 번째 키워드는 요청 간 지수를 맞추는 기준(anchor)으로도 쓰이므로,
# 검색량이 아주 적지 않은 일반적인 단어를 두는 편이 좋다.
DEFAULT_POOL = [
    "지방소멸",
    "인구감소",
    "청년 유입",
    "학령인구",
    "폐교",
    "관광객",
    "지역축제",
    "산업단지",
    "귀농귀촌",
    "재난안전",
    "노후 인프라",
    "농산물 가격",
]
TOP_N = 5

# 기간 옵션: 프론트가 보내는 값 → (네이버 timeUnit, 조회 범위(일), 표시 문구)
PERIODS = {
    "daily": ("date", 30, "최근 30일"),
    "weekly": ("week", 56, "최근 8주"),
    "monthly": ("month", 365, "최근 12개월"),
}
DEFAULT_PERIOD = "weekly"

# 집계 단위가 일/주/월이라 자주 부를 필요가 없다. 1시간 캐시로 호출량을 아낀다.
# 기간별로 결과가 다르므로 캐시도 기간별로 나눠 보관한다.
_CACHE: dict[str, dict] = {}
CACHE_TTL = 3600


MAX_POOL = 20  # 요청 수(5개 단위 분할) 상한을 두어 호출량을 통제한다


def _pool(keywords: list[str] | None = None) -> list[str]:
    """조회할 키워드 풀. 호출자가 지정하면 그것을, 없으면 환경변수 → 기본값 순."""
    if keywords:
        cleaned = [k.strip() for k in keywords if k and k.strip()]
        if cleaned:
            return list(dict.fromkeys(cleaned))[:MAX_POOL]  # 중복 제거 + 상한
    raw = os.environ.get("TREND_KEYWORDS", "")
    parsed = [k.strip() for k in raw.split(",") if k.strip()]
    return parsed or DEFAULT_POOL


def get_trends(
    access_code_id: str,
    period: str = DEFAULT_PERIOD,
    keywords: list[str] | None = None,
    force: bool = False,
) -> dict:
    """검색지수 상위 키워드. period: daily | weekly | monthly."""
    if period not in PERIODS:
        period = DEFAULT_PERIOD
    time_unit, span_days, label = PERIODS[period]
    pool = _pool(keywords)
    cache_key = f"{period}|{','.join(pool)}"  # 기간·키워드 조합별로 캐시를 나눈다

    if not naver.is_configured():
        raise HTTPException(
            status_code=502,
            detail=(
                "네이버 API 키가 설정되지 않았습니다. "
                "환경변수 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 를 추가한 뒤 재배포하세요."
            ),
        )

    now = time.time()
    cached = _CACHE.get(cache_key)
    if not force and cached and now - cached["at"] < CACHE_TTL:
        return cached["data"]

    try:
        items = naver.top_keywords(
            pool, limit=max(TOP_N, len(pool)), time_unit=time_unit, span_days=span_days
        )
    except naver.NaverError as exc:
        logger.warning("네이버 트렌드 호출 실패: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("네이버 트렌드 처리 중 오류")
        raise HTTPException(
            status_code=502, detail=f"트렌드 조회 중 오류: {type(exc).__name__}: {exc}"
        ) from exc

    if not items:
        raise HTTPException(
            status_code=502, detail="네이버에서 트렌드 데이터를 받지 못했습니다 (응답이 비어 있음)."
        )

    data = {
        "keywords": items,
        "period": period,
        "period_label": label,
        "queried": pool,
    }
    _CACHE[cache_key] = {"at": now, "data": data}
    return data
