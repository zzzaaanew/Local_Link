"""AI가 만든 추천물 보관.

지금까지는 기자가 '선택한' 것만 DB에 남고, 무엇을 보여줬는지는 사라졌다.
그래서 추천 품질을 되짚어볼 수가 없었다. 이제 생성 시점에 전부 저장하고,
기자가 고른 항목에 표시(picked)를 남긴다.

세 기능이 한 테이블(suggestions)을 공유한다.
  plan            오늘의 발제 취재 제안서
  press_pitch     보도자료 발 발제 후보
  rewrite_target  리라이팅 후보 기사

저장 실패가 기능을 막지 않도록 예외는 삼키고 로그만 남긴다 — 보관은 부가
기능이고, 기자가 화면에서 결과를 못 받는 쪽이 더 나쁘다.
"""
import logging
import uuid

from db import supabase

logger = logging.getLogger(__name__)

# 화면 카드 → DB 컬럼 매핑 (종류마다 들어오는 필드 이름이 다르다)
_FIELDS = {
    "plan": {
        "org": "agency",
        "region": "region",
        "timing": "timing",
        "scheduled_at": "scheduled_at",
        "body": "plan_markdown",
    },
    "press_pitch": {
        "org": "org",
        "region": "region",
        "timing": "tag",
    },
    "rewrite_target": {
        "org": "source",
        "scheduled_at": "published_at",
        "url": "url",
        "why": "local_angle",
    },
}


def save_batch(
    access_code_id: str,
    kind: str,
    items: list[dict],
    session_id: str | None = None,
) -> str | None:
    """생성된 묶음을 저장하고, 각 항목에 DB id를 채워 넣는다.

    items 는 제자리에서 수정된다 — 화면으로 내려갈 카드가 자기 id를 갖게 되어,
    나중에 '이걸 골랐다'고 알려줄 수 있다.
    반환: batch_id (실패 시 None)
    """
    if not items:
        return None

    batch_id = str(uuid.uuid4())
    field_map = _FIELDS.get(kind, {})

    rows = []
    for i, item in enumerate(items):
        row = {
            "access_code_id": access_code_id,
            "session_id": session_id,
            "kind": kind,
            "batch_id": batch_id,
            "position": i + 1,
            "title": (item.get("title") or "(제목 없음)")[:500],
            "summary": item.get("summary"),
            "why": item.get("why"),
        }
        for column, source_key in field_map.items():
            row[column] = item.get(source_key)
        rows.append(row)

    try:
        saved = supabase.table("suggestions").insert(rows).execute().data or []
    except Exception as exc:
        logger.warning("추천물 저장 실패 (kind=%s): %s", kind, exc)
        return None

    # position 순서대로 id를 되돌려 카드에 붙인다
    by_position = {r["position"]: r["id"] for r in saved}
    for i, item in enumerate(items):
        item["suggestion_id"] = by_position.get(i + 1)

    return batch_id


def mark_picked(
    access_code_id: str, suggestion_id: str | None, pitch_id: str | None = None
) -> None:
    """기자가 고른 추천물에 표시. 남의 코드 데이터는 건드리지 않는다."""
    if not suggestion_id:
        return
    try:
        supabase.table("suggestions").update(
            {"picked": True, "picked_at": "now()", "pitch_id": pitch_id}
        ).eq("id", suggestion_id).eq("access_code_id", access_code_id).execute()
    except Exception as exc:
        logger.warning("추천물 선택 표시 실패 (id=%s): %s", suggestion_id, exc)


def create_source_session(
    access_code_id: str, source_title: str, source_text: str
) -> str | None:
    """보도자료 원문을 발제 생성 시점에 저장한다.

    예전에는 기자가 '이 아이템으로 시작'을 눌러야 세션이 만들어져서, 발제만
    뽑아보고 고르지 않으면 입력한 보도자료가 사라졌다.
    """
    try:
        row = (
            supabase.table("sessions")
            .insert(
                {
                    "access_code_id": access_code_id,
                    "source_text": source_text,
                    "source_title": source_title or None,
                    "article_kind": "press",
                }
            )
            .execute()
            .data[0]
        )
        return row["id"]
    except Exception as exc:
        logger.warning("보도자료 세션 저장 실패: %s", exc)
        return None
