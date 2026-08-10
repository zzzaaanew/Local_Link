"""프롬프트 조합 모듈.

시스템 프롬프트는 txt 파일에서 읽고(load_prompt), 요청마다 달라지는 데이터
(스타일북·발제·취재물·원문)는 여기서 사용자 메시지로 조립한다.
프롬프트 내용을 바꾸고 싶으면 prompts/*.txt 만 교체하면 된다.
"""
from pathlib import Path

PROMPT_DIR = Path(__file__).parent
MAX_PRESS_CHARS = 8000  # 원문 길이 제한 (토큰 비용 통제)


def load_prompt(name: str) -> str:
    """이름에 해당하는 프롬프트 파일({name}.txt)을 읽는 범용 로더.

    요청마다 파일을 다시 읽으므로, 파일을 고치면 서버 재시작 없이 반영된다.
    """
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")


def build_draft_message(
    source_title: str,
    source_text: str,
    pitch: dict,
    research_notes: list[str] | None = None,
    stylebook_block: str = "",
) -> str:
    """초안 생성용 사용자 메시지.

    스타일북 + 선택된 발제 + 취재 질문 + 취재물 + 보도자료 원문을 조합한다.
    시스템 프롬프트는 rewrite.txt 를 쓴다(리라이팅과 같은 문체 규칙을 공유).
    """
    parts = []
    if stylebook_block:
        parts.append(stylebook_block)  # 프롬프트가 '최우선 적용'하도록 맨 앞에 둔다

    parts.append(
        "[선택된 발제]\n"
        f"제목: {pitch.get('title') or ''}\n"
        f"요약: {pitch.get('summary') or ''}\n"
        f"발제 가치: {pitch.get('why') or ''}\n"
        f"근거: {pitch.get('source_basis') or ''}"
    )

    questions = pitch.get("questions") or []
    if questions:
        parts.append("[발제의 취재 질문]\n" + "\n".join(f"- {q}" for q in questions))

    if research_notes:
        joined = "\n\n".join(f"- {n}" for n in research_notes)
        parts.append(f"[기자가 수집한 취재물]\n{joined}")

    parts.append(f"[보도자료 제목]\n{source_title.strip() or '(제목 없음)'}")
    parts.append(f"[보도자료 원문]\n{source_text.strip()[:MAX_PRESS_CHARS]}")
    parts.append(
        "위 발제의 각도로, 취재물에서 확인된 내용을 반영해 기사를 작성하고 "
        "'8. 출력 형식'의 JSON으로만 출력하라."
    )
    return "\n\n".join(parts)


def build_rewrite_message(
    source_title: str,
    source_text: str,
    headline_count: int = 3,
    user_prompt: str | None = None,
    stylebook_block: str = "",
) -> str:
    """리라이팅용 사용자 메시지. 스타일북 + 기자 요청 + 원문을 조합."""
    parts = []
    if stylebook_block:
        parts.append(stylebook_block)
    if user_prompt and user_prompt.strip():
        parts.append(f"[기자의 요청사항]\n{user_prompt.strip()}")
    parts.append(f"[헤드라인 개수]\n{headline_count}")
    parts.append(f"[원문 제목]\n{source_title.strip() or '(제목 없음)'}")
    parts.append(f"[원문]\n{source_text.strip()[:MAX_PRESS_CHARS]}")
    parts.append("'8. 출력 형식'의 JSON으로만 출력하라.")
    return "\n\n".join(parts)

