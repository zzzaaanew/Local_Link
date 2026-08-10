"""네이버 API Hub — Search Trend (검색어 트렌드) 클라이언트.

인증: 헤더 X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY (NCP API Gateway)

환경변수:
  NAVER_CLIENT_ID      NCP Client ID
  NAVER_CLIENT_SECRET  NCP Client Secret
  NAVER_TREND_URL      엔드포인트 재정의 (선택)

주의: 이 API는 '인기 검색어 목록'을 제공하지 않는다. 조회할 키워드를 직접
넘겨야 하고, 응답은 요청에 포함된 키워드들 사이의 상대 지수(최댓값 100)다.
따라서 상위권을 만들려면 후보 풀을 조회한 뒤 지수로 정렬해야 한다.
또한 지수는 '요청 단위'로 정규화되므로, 여러 번 나눠 호출할 때는 공통 기준
키워드(anchor)를 끼워 넣어 비교 가능하게 보정한다.
"""
import json
import logging
import os
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 15.0
DEFAULT_URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
MAX_GROUPS = 5  # 요청당 키워드 그룹 최대 개수


class NaverError(Exception):
    """네이버 API 호출 실패. 메시지에 사용자에게 보여줄 원인을 담는다."""


def _clean(name: str) -> str:
    # 환경변수에 앞뒤 공백·따옴표가 섞여 들어오는 일이 잦아 정리한다.
    return os.environ.get(name, "").strip().strip('"').strip("'")


def is_configured() -> bool:
    return bool(_clean("NAVER_CLIENT_ID") and _clean("NAVER_CLIENT_SECRET"))


def _headers() -> dict:
    return {
        "X-NCP-APIGW-API-KEY-ID": _clean("NAVER_CLIENT_ID"),
        "X-NCP-APIGW-API-KEY": _clean("NAVER_CLIENT_SECRET"),
        "Content-Type": "application/json",
    }


def _url() -> str:
    return _clean("NAVER_TREND_URL") or DEFAULT_URL


def _call(keywords: list[str], time_unit: str, span_days: int) -> dict:
    end = date.today()
    start = end - timedelta(days=span_days)
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "timeUnit": time_unit,  # date(일간) | week(주간) | month(월간)
        "keywordGroups": [{"groupName": k, "keywords": [k]} for k in keywords],
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            res = client.post(_url(), headers=_headers(), json=body)
    except httpx.HTTPError as exc:
        raise NaverError(f"네이버 서버에 연결하지 못했습니다: {type(exc).__name__}") from exc

    if res.status_code != 200:
        raise NaverError(_error_message(res.status_code, res.text))
    return res.json()


def top_keywords(
    pool: list[str], limit: int = 5, time_unit: str = "week", span_days: int = 56
) -> list[dict]:
    """후보 키워드 풀을 조회해 검색량 상위 keyword 를 골라낸다.

    time_unit: date(일간) | week(주간) | month(월간)
    반환: [{"keyword", "score", "change_pct"}] — 검색지수 내림차순, 최대 limit개
    """
    if not pool:
        return []

    anchor = pool[0]
    chunks = _chunk_with_anchor(pool, anchor)

    scored: dict[str, dict] = {}
    for chunk in chunks:
        data = _call(chunk, time_unit, span_days)
        groups = {g.get("title", ""): g.get("data", []) for g in data.get("results", [])}

        # 이 요청 안에서 anchor 가 받은 지수로 스케일을 맞춰, 요청이 달라도 비교 가능하게 한다.
        anchor_value = _latest(groups.get(anchor, [])) if anchor in groups else 0
        scale = (100 / anchor_value) if anchor_value > 0 else 1

        for keyword, points in groups.items():
            if not points or keyword in scored:
                continue
            scored[keyword] = {
                "keyword": keyword,
                "score": round(_latest(points) * scale, 1),
                "change_pct": _change_pct(points),
            }

    ranked = sorted(scored.values(), key=lambda r: r["score"], reverse=True)
    return ranked[:limit]


def _chunk_with_anchor(pool: list[str], anchor: str) -> list[list[str]]:
    """풀을 요청 단위로 쪼갠다. 첫 묶음 외에는 anchor 를 함께 넣어 기준을 맞춘다."""
    first, rest = pool[:MAX_GROUPS], pool[MAX_GROUPS:]
    chunks = [first]
    step = MAX_GROUPS - 1  # anchor 자리 하나를 비워둔다
    for i in range(0, len(rest), step):
        chunks.append([anchor] + rest[i : i + step])
    return chunks


def _latest(points: list[dict]) -> float:
    return float(points[-1].get("ratio", 0)) if points else 0.0


def _change_pct(points: list[dict]) -> int:
    """마지막 구간과 직전 구간의 상대 변화율(%). 데이터가 부족하면 0."""
    if len(points) < 2:
        return 0
    prev = float(points[-2].get("ratio", 0))
    last = float(points[-1].get("ratio", 0))
    if prev <= 0:
        return 0
    return round((last - prev) / prev * 100)


def _error_message(status: int, text: str) -> str:
    """네이버 오류 응답을 사람이 읽고 바로 조치할 수 있는 문장으로 바꾼다."""
    detail = ""
    try:
        parsed = json.loads(text)
        detail = (
            parsed.get("errorMessage")
            or parsed.get("message")
            or (parsed.get("error") or {}).get("details", "")
            or (parsed.get("error") or {}).get("message", "")
        )
    except Exception:
        detail = (text or "")[:200]

    if "subscription" in (detail or "").lower():
        return (
            "네이버 클라우드 플랫폼 콘솔에서 Search Trend 이용 신청이 되어 있지 않습니다. "
            "신청을 완료한 뒤 다시 시도하세요."
        )
    if status in (401, 403):
        return (
            f"네이버 인증 실패 (HTTP {status}): {detail} "
            "— Client ID/Secret 값과 Search Trend 이용 신청 여부를 확인하세요."
        )
    if status == 429:
        return f"네이버 API 호출 한도를 초과했습니다 (HTTP 429): {detail}"
    return f"네이버 API 오류 (HTTP {status}): {detail}"
