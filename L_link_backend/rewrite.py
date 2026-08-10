"""기사·보도자료 리라이팅.

원문 + 자사 스타일북 + (선택)기자 요청을 받아 본문과 헤드라인 후보를 생성한다.
원문은 sessions(article_kind='rewrite')로, 결과는 drafts(kind='rewrite')로 저장해
초안 테이블을 재사용한다.

시스템 프롬프트는 prompts/rewrite.txt 하나뿐이다. 예전에는 '단신/리라이팅' 모드로
길이를 나눴지만, 스타일북이 문체·구성을 정하므로 모드 구분을 없앴다.
"""
import llm
import stylebook
import usage as usage_service
from db import supabase
from prompts.builder import build_rewrite_message, load_prompt


def rewrite_press_release(
    access_code_id: str,
    source_text: str,
    source_title: str,
    user_prompt: str | None = None,
    headline_count: int = 3,
) -> dict:
    session = (
        supabase.table("sessions")
        .insert(
            {
                "access_code_id": access_code_id,
                "source_text": source_text,
                "source_title": source_title,
                "user_prompt": user_prompt,
                "article_kind": "rewrite",
            }
        )
        .execute()
        .data[0]
    )

    user_message = build_rewrite_message(
        source_title=source_title,
        source_text=source_text,
        headline_count=headline_count,
        user_prompt=user_prompt,
        stylebook_block=stylebook.as_prompt_block(),
    )

    result, usage = llm.rewrite_press_release(load_prompt("rewrite"), user_message)
    body = result.get("body", "")
    headlines = (result.get("headlines") or [])[:headline_count]

    draft = (
        supabase.table("drafts")
        .insert(
            {
                "session_id": session["id"],
                "pitch_id": None,
                "kind": "rewrite",
                "headline_count": headline_count,
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

    usage_service.log(access_code_id, "rewrite", usage, session_id=session["id"])

    return {
        "draft_id": draft["id"],
        "session_id": session["id"],
        "headline_count": headline_count,
        "body": body,
        "headlines": headlines,
    }
