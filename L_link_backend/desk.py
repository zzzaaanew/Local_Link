"""'내가 선택한 발제' 데스크 — 선택 발제 + 취재 + 초안 저장/조회 + 완성 기사 입력.

두 가지 흐름이 같은 테이블 구조를 공유한다(테이블 난립 방지).

  ① 보도자료 발 발제  select_pitch() → add_research_and_draft()
     sessions(article_kind='press', source_text=보도자료 원문)
       → pitches(status='selected')            ← '이 아이템으로 시작'
       → research_notes(취재 입력, **필수**)     ← 데스크에서 이어서 작성
       → drafts(kind='draft_deep', body_text=초안)

  ② 주간기획 취재 제안서  save_plan()
     sessions(article_kind='source') → pitches(status='selected')
       → drafts(kind='plan', body_text=계획서)

완성 기사는 두 경우 모두 기존 articles 테이블에 제출한다.

취재 없이 초안을 만들면 할루시네이션 위험이 크기 때문에, ①은 취재 내용 없이
초안 단계로 넘어갈 수 없다.
"""
import llm
import stylebook
import usage as usage_service
from fastapi import HTTPException
from prompts.builder import build_draft_message, load_prompt

from db import supabase


def select_pitch(access_code_id: str, pitch: dict, session_id: str | None = None) -> dict:
    """보도자료 발 발제에서 '이 아이템으로 시작'.

    아직 취재 전이므로 초안은 만들지 않는다. 발제만 저장해 두면 기자가 데스크에서
    이어서 취재 내용을 넣고 초안을 만들 수 있다.

    session_id: 발제 생성 시점에 이미 만들어 둔 보도자료 세션. 그걸 재사용하면
    같은 보도자료로 발제를 두 건 고를 때 원문이 중복 저장되지 않는다.
    """
    title = (pitch.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="발제 제목이 없습니다.")

    session_id = _reuse_session(access_code_id, session_id) or _new_press_session(
        access_code_id, pitch, title
    )

    saved = (
        supabase.table("pitches")
        .insert(
            {
                "session_id": session_id,
                "tag": pitch.get("tag"),
                "title": title,
                "summary": pitch.get("summary"),
                "why": pitch.get("why"),
                "source_basis": pitch.get("source_basis"),
                "questions": pitch.get("questions") or [],
                "interview_targets": pitch.get("interview_targets") or [],
                "data_to_check": pitch.get("data_to_check") or [],
                "status": "selected",
            }
        )
        .execute()
        .data[0]
    )

    return {
        "pitch_id": saved["id"],
        "session_id": session_id,
        "message": "발제를 저장했습니다. 취재 내용을 입력하면 초안을 만들 수 있어요.",
    }


def _reuse_session(access_code_id: str, session_id: str | None) -> str | None:
    """넘어온 세션이 이 코드의 것인지 확인하고 그대로 쓴다. 아니면 None."""
    if not session_id:
        return None
    res = (
        supabase.table("sessions")
        .select("id")
        .eq("id", session_id)
        .eq("access_code_id", access_code_id)
        .limit(1)
        .execute()
    )
    return res.data[0]["id"] if res.data else None


def _new_press_session(access_code_id: str, pitch: dict, title: str) -> str:
    """세션이 없을 때만 만든다 (구버전 프론트 호환)."""
    row = (
        supabase.table("sessions")
        .insert(
            {
                "access_code_id": access_code_id,
                "source_text": _pitch_context(pitch),
                "source_title": pitch.get("press_title") or title,
                "article_kind": "press",
            }
        )
        .execute()
        .data[0]
    )
    return row["id"]


def get_item(access_code_id: str, pitch_id: str) -> dict:
    """데스크 항목 하나 (발제 + 취재물 + 초안). 남의 코드 데이터는 조회되지 않는다."""
    res = (
        supabase.table("pitches")
        .select("*, sessions!inner(access_code_id, source_text, source_title, article_kind)")
        .eq("id", pitch_id)
        .eq("sessions.access_code_id", access_code_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="발제를 찾을 수 없습니다.")

    pitch = res.data[0]
    notes = (
        supabase.table("research_notes")
        .select("*")
        .eq("pitch_id", pitch_id)
        .order("created_at")
        .execute()
        .data
        or []
    )
    drafts = (
        supabase.table("drafts")
        .select("*")
        .eq("pitch_id", pitch_id)
        .order("created_at")
        .execute()
        .data
        or []
    )
    return {
        "pitch": pitch,
        "session_id": pitch["session_id"],
        "research_notes": [n["content"] for n in notes],
        "latest_draft": drafts[-1] if drafts else None,
    }


def add_research_and_draft(access_code_id: str, pitch_id: str, research_text: str) -> dict:
    """취재 내용을 저장하고 초안을 생성한다.

    취재 내용은 필수다. 보도자료만 가지고 초안을 쓰면 없는 사실을 지어낼 위험이
    커서, 이 흐름에서는 '건너뛰기'를 두지 않는다.
    """
    text = (research_text or "").strip()
    if len(text) < 20:
        raise HTTPException(
            status_code=422,
            detail="취재 내용을 20자 이상 입력해주세요. 취재 없이는 초안을 만들지 않습니다.",
        )

    item = get_item(access_code_id, pitch_id)
    pitch = item["pitch"]
    session = pitch["sessions"]

    supabase.table("research_notes").insert({"pitch_id": pitch_id, "content": text}).execute()
    notes = item["research_notes"] + [text]

    # 시스템 프롬프트는 리라이팅과 같은 rewrite.txt 를 쓴다.
    # 문체·인용·사실확인 규칙이 동일해야 기사 결과물이 한 신문처럼 읽힌다.
    user_message = build_draft_message(
        source_title=session.get("source_title") or "",
        source_text=session.get("source_text") or "",
        pitch=pitch,
        research_notes=notes,
        stylebook_block=stylebook.as_prompt_block(),
    )
    result, usage = llm.rewrite_press_release(load_prompt("rewrite"), user_message)
    body = result.get("body", "")
    headlines = (result.get("headlines") or [])[:3]

    draft = (
        supabase.table("drafts")
        .insert(
            {
                "session_id": pitch["session_id"],
                "pitch_id": pitch_id,
                "kind": "draft_deep",
                "body_text": body,
                "headlines": headlines,
                "model": usage["model"],
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
            }
        )
        .execute()
        .data[0]
    )

    supabase.table("pitches").update({"status": "draft_completed"}).eq("id", pitch_id).execute()
    usage_service.log(access_code_id, "draft", usage, session_id=pitch["session_id"])

    return {
        "draft_id": draft["id"],
        "body": body,
        "headlines": headlines,
        "research_count": len(notes),
    }


def save_plan(access_code_id: str, pitch: dict, plan_markdown: str) -> dict:
    """주간기획 취재 계획서를 저장한다.

    취재→초안 단계가 없는 흐름이므로 계획서 자체를 drafts(kind='plan')로 남긴다.
    기존 테이블을 그대로 재사용해 '내가 선택한 발제'에서 함께 조회된다.
    """
    plan = (plan_markdown or "").strip()
    if not plan:
        raise HTTPException(status_code=422, detail="저장할 계획서 내용이 없습니다.")

    # 취재 제안서는 원문이 없다. 예전에는 source_text 가 NOT NULL 이라 발제 메타를
    # 합성해 채워 넣었지만, 그건 원문이 아니어서 오해를 낳았다. 이제 비워 둔다.
    session = (
        supabase.table("sessions")
        .insert(
            {
                "access_code_id": access_code_id,
                "source_text": None,
                "source_title": pitch.get("title") or "(제목 없음)",
                "article_kind": "source",
            }
        )
        .execute()
        .data[0]
    )

    saved_pitch = (
        supabase.table("pitches")
        .insert(
            {
                "session_id": session["id"],
                "tag": pitch.get("timing"),
                "title": pitch.get("title") or "(제목 없음)",
                "summary": pitch.get("summary"),
                "why": pitch.get("why"),
                "source_basis": _basis(pitch),
                "questions": [],
                "interview_targets": [],
                "data_to_check": [],
                "status": "selected",
            }
        )
        .execute()
        .data[0]
    )

    draft = (
        supabase.table("drafts")
        .insert(
            {
                "session_id": session["id"],
                "pitch_id": saved_pitch["id"],
                "kind": "plan",
                "body_text": plan,
            }
        )
        .execute()
        .data[0]
    )

    return {
        "pitch_id": saved_pitch["id"],
        "session_id": session["id"],
        "draft_id": draft["id"],
        "message": "저장했습니다. '내가 선택한 발제'에서 확인할 수 있어요.",
    }


def _basis(pitch: dict) -> str:
    bits = [pitch.get("agency"), pitch.get("scheduled_at"), pitch.get("timing")]
    return " / ".join(b for b in bits if b)


def submit_article(
    access_code_id: str,
    session_id: str,
    pitch_id: str | None,
    article_url: str | None,
    article_text: str | None,
) -> dict:
    """완성 기사 등록. 발제가 실제 기사로 이어졌는지 확인하는 용도."""
    if not article_url and not article_text:
        raise HTTPException(status_code=422, detail="기사 URL 또는 본문 중 하나는 입력해야 합니다.")

    session_res = (
        supabase.table("sessions")
        .select("access_code_id")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    if session_res.data["access_code_id"] != access_code_id:
        raise HTTPException(status_code=403, detail="이 세션에 접근할 수 없습니다.")

    res = (
        supabase.table("articles")
        .insert(
            {
                "session_id": session_id,
                "pitch_id": pitch_id,
                "article_url": article_url,
                "article_text": article_text,
            }
        )
        .execute()
    )
    return {"article_id": res.data[0]["id"], "message": "기사를 등록했습니다."}


def list_desk(access_code_id: str) -> list[dict]:
    """내가 선택한 발제 목록 + 각 발제의 취재물·초안·제출 기사."""
    pitch_res = (
        supabase.table("pitches")
        .select("*, sessions!inner(access_code_id, source_title, article_kind, created_at)")
        # archived 는 구버전에서 넘어온 미선택 발제 — 데스크에 띄우지 않는다
        .in_("status", ["selected", "draft_completed"])
        .eq("sessions.access_code_id", access_code_id)
        .order("created_at", desc=True)
        .execute()
    )
    pitches = pitch_res.data or []
    if not pitches:
        return []

    ids = [p["id"] for p in pitches]
    drafts = supabase.table("drafts").select("*").in_("pitch_id", ids).order("created_at").execute().data or []
    notes = (
        supabase.table("research_notes").select("*").in_("pitch_id", ids).order("created_at").execute().data or []
    )
    session_ids = list({p["session_id"] for p in pitches})
    articles = (
        supabase.table("articles").select("*").in_("session_id", session_ids).execute().data or []
    )

    items = []
    for p in pitches:
        p_drafts = [d for d in drafts if d["pitch_id"] == p["id"]]
        items.append(
            {
                "pitch": p,
                "session_id": p["session_id"],
                "research_notes": [n["content"] for n in notes if n["pitch_id"] == p["id"]],
                "latest_draft": p_drafts[-1] if p_drafts else None,
                "article": next((a for a in articles if a["session_id"] == p["session_id"]), None),
            }
        )
    return items


def _pitch_context(pitch: dict) -> str:
    """세션 본문으로 보관할 원문/맥락 (재열람·재생성용).

    보도자료 발 발제는 실제 원문이 있으므로 그대로 저장하고,
    원천기사 발제는 원문이 없어 발제 맥락을 합성해 저장한다.
    """
    press_source = (pitch.get("press_source") or "").strip()
    if press_source:
        return press_source

    parts = [
        f"[발제] {pitch.get('title', '')}",
        f"요약: {pitch.get('summary', '')}",
        f"기사 가치: {pitch.get('why', '')}",
        f"근거: {pitch.get('source_basis', '')}",
        f"기관/지역: {pitch.get('org', '')} / {pitch.get('region', '')}",
    ]
    return "\n".join(parts)
