"""사용량 기록과 일일 한도.

이전 구조는 'generate'/'refresh' 두 액션만 세었는데 그 액션을 쓰던 코드가
사라지면서 집계가 항상 0이 되고 한도도 걸리지 않았다. 여기서 다시 세운다.

원칙
  1. **모든 LLM 호출을 기록한다.** 비용을 보려면 빠짐없이 남아야 한다.
  2. **한도는 기자가 버튼을 눌러 일으킨 생성에만 건다.**
     화면에 들어가면 자동으로 도는 것(첫 접속 발제 추천, 리라이팅 후보 발굴)까지
     세면 페이지를 연 것만으로 한도가 깎여 억울하다. → billable=False 로 남긴다.
  3. 한도 확인은 생성 **직전**에, 기록은 생성 **직후**에 한다.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from db import supabase

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 액션 → 화면에 보여줄 이름 (한도 초과 안내에 쓴다)
ACTIONS = {
    "plan": "오늘의 발제 추천",
    "press_pitch": "보도자료 발 발제",
    "rewrite_target": "리라이팅 후보 발굴",
    "rewrite": "리라이팅",
    "draft": "기사 초안",
}

# 액션별 하루 상한. 전체 한도(daily_limit)와 **별도로** 걸린다.
#
# 리라이팅 후보 발굴은 화면에 들어가기만 해도 자동으로 도는데, 기사 120건
# 목록을 통째로 넣는 호출이라 한 번에 나가는 토큰이 크다. 전체 한도에서 빼는
# 대신(자동 실행이므로) 이 액션만의 상한을 둬서 페이지를 반복해 열어도
# 비용이 무한정 늘지 않게 막는다.
ACTION_DAILY_LIMITS = {
    "rewrite_target": 5,
}


def today_start() -> datetime:
    """한국 시간 자정. 사용량은 KST 자정에 리셋된다."""
    return datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)


def get_daily(access_code_id: str) -> dict:
    """오늘 사용량 → {"used", "limit", "remaining"}.

    표시용(GET /api/usage)과 강제용(require_quota)이 같은 계산을 쓰도록 한 곳에 뒀다.
    """
    code_res = (
        supabase.table("access_codes")
        .select("daily_limit, is_active")
        .eq("id", access_code_id)
        .single()
        .execute()
    )
    if not code_res.data or not code_res.data["is_active"]:
        raise HTTPException(status_code=401, detail="코드가 비활성화되었습니다.")

    res = (
        supabase.table("usage_logs")
        .select("id", count="exact")
        .eq("access_code_id", access_code_id)
        .eq("billable", True)
        .gte("created_at", today_start().isoformat())
        .execute()
    )
    used = res.count or 0
    limit = code_res.data["daily_limit"]
    return {"used": used, "limit": limit, "remaining": max(limit - used, 0)}


def action_count_today(access_code_id: str, action: str) -> int:
    """오늘 이 액션을 몇 번 썼나. 자동 실행분(billable=False)까지 전부 센다."""
    res = (
        supabase.table("usage_logs")
        .select("id", count="exact")
        .eq("access_code_id", access_code_id)
        .eq("action", action)
        .gte("created_at", today_start().isoformat())
        .execute()
    )
    return res.count or 0


def require_quota(access_code_id: str, action: str, billable: bool = True) -> None:
    """생성 직전 호출. 한도를 넘었으면 429로 막는다.

    두 가지를 본다.
      1. 액션별 상한 (ACTION_DAILY_LIMITS) — 자동 실행분까지 포함해 센다
      2. 전체 일일 한도 (access_codes.daily_limit) — billable 인 호출만 센다
    """
    label = ACTIONS.get(action, action)

    action_limit = ACTION_DAILY_LIMITS.get(action)
    if action_limit is not None:
        used = action_count_today(access_code_id, action)
        if used >= action_limit:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"{label}은(는) 하루 {action_limit}회까지 이용할 수 있습니다. "
                    "내일 다시 시도해주세요."
                ),
            )

    if not billable:
        return

    usage = get_daily(access_code_id)
    if usage["used"] >= usage["limit"]:
        raise HTTPException(
            status_code=429,
            detail=(
                f"오늘 생성 한도({usage['limit']}회)를 모두 사용했습니다. "
                f"내일 다시 이용해주세요. (요청: {label})"
            ),
        )


def log(
    access_code_id: str,
    action: str,
    usage: dict | None = None,
    session_id: str | None = None,
    billable: bool = True,
) -> None:
    """LLM 호출 1건 기록.

    usage: llm 모듈이 돌려주는 {"model", "input_tokens", "output_tokens"}.
    기록 실패가 기능을 막지 않도록 예외는 삼키고 로그만 남긴다.
    """
    row = {
        "access_code_id": access_code_id,
        "session_id": session_id,
        "action": action,
        "billable": billable,
    }
    if usage:
        row["model"] = usage.get("model")
        row["input_tokens"] = usage.get("input_tokens")
        row["output_tokens"] = usage.get("output_tokens")

    try:
        supabase.table("usage_logs").insert(row).execute()
    except Exception as exc:
        logger.warning("사용량 기록 실패 (action=%s): %s", action, exc)
