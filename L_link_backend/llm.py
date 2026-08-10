"""Claude API 호출 모듈.

- 발제 3개를 JSON으로 받는다.
- 응답의 usage(입력/출력 토큰)를 함께 반환해 usage_logs에 기록한다.
- 프롬프트 내용은 이 파일이 모른다. prompts/builder.py가 조합해서 넘겨준다.
"""
import json
import logging
import os

import anthropic
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    timeout=90.0,
)

# 모델은 환경변수로 교체 가능하게. 발제 품질/비용 균형상 Sonnet 권장.
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 3000
DRAFT_MAX_TOKENS = 6000    # 초안(특히 심층형)은 분량이 길어 여유를 둔다
REWRITE_MAX_TOKENS = 6000  # 리라이팅 본문 + 헤드라인

# 주의: Claude Sonnet 5(및 Opus 4.7+)는 temperature/top_p/top_k를 기본값이
# 아닌 값으로 주면 400 에러를 반환한다. adaptive thinking과 함께 도입된
# 제약이라 샘플링 파라미터 대신 effort로 결과의 일관성/깊이를 조절한다.
# 또한 assistant 메시지 prefill도 Sonnet 4.6 이후 모델에서 400 에러이므로
# JSON 강제는 prefill이 아니라 system_prompt 지시문에 전적으로 의존한다.
EFFORT = os.environ.get("ANTHROPIC_EFFORT", "medium")  # low/medium/high(기본)/xhigh/max


# ------------------------------------------------------------
# 초안 / 리라이팅 / 톤 요약 (작업 A·B)
# generate_pitches와 동일한 호출 패턴을 공유 헬퍼로 재사용한다.
# (generate_pitches 자체는 회귀 방지를 위해 수정하지 않음)
# ------------------------------------------------------------

def _call_claude(
    system_prompt: str, user_message: str, max_tokens: int, model: str | None = None
) -> tuple[str, dict]:
    """공통 Claude 호출. (raw_text, usage) 반환. 발제 경로와 동일한 제약을 따른다.

    model을 주면 그 모델로 호출한다 (예: 선별 단계는 저렴한 Haiku).
    """
    try:
        response = client.messages.create(
            model=model or MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            output_config={"effort": EFFORT},
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"AI 호출 실패: {exc.status_code}"
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise HTTPException(
            status_code=502,
            detail="AI 서버에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.",
        ) from exc

    raw_text = "".join(block.text for block in response.content if block.type == "text")

    if response.stop_reason == "max_tokens":
        logger.warning("Claude 응답이 max_tokens로 잘림 (model=%s)", MODEL)
        raise HTTPException(
            status_code=502, detail="AI 응답이 너무 길어 잘렸습니다. 다시 시도해주세요."
        )

    usage = {
        "model": response.model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return raw_text, usage


def _parse_json_object(raw_text: str) -> dict:
    """LLM 응답에서 단일 JSON 객체를 안전하게 파싱한다 (마크다운 펜스 제거)."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        logger.warning("Claude 응답에서 JSON 경계를 찾지 못함: %.500r", raw_text)
        raise HTTPException(status_code=502, detail="AI 응답 형식 오류입니다. 다시 시도해주세요.")

    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        logger.warning("Claude 응답 JSON 파싱 실패: %.500r", raw_text)
        raise HTTPException(
            status_code=502, detail="AI 응답을 해석하지 못했습니다. 다시 시도해주세요."
        ) from exc


def rewrite_press_release(system_prompt: str, user_message: str) -> tuple[dict, dict]:
    """리라이팅. 반환: ({"body", "headlines"}, usage)."""
    raw_text, usage = _call_claude(system_prompt, user_message, REWRITE_MAX_TOKENS)
    result = _parse_json_object(raw_text)
    if "body" not in result:
        raise HTTPException(
            status_code=502, detail="AI 리라이팅 응답 형식 오류입니다. 다시 시도해주세요."
        )
    result.setdefault("headlines", [])
    return result, usage


def merge_usage(*usages: dict | None) -> dict:
    """여러 번의 LLM 호출 토큰을 하나로 합친다.

    한 기능이 저비용 필터 + 본 생성처럼 두 번 호출하는 경우가 있어, 사용량
    기록에는 합계를 남긴다. model 은 가장 비싼(마지막) 호출 것을 대표로 쓴다.
    """
    total = {"model": None, "input_tokens": 0, "output_tokens": 0}
    for u in usages:
        if not u:
            continue
        total["input_tokens"] += u.get("input_tokens") or 0
        total["output_tokens"] += u.get("output_tokens") or 0
        if u.get("model"):
            total["model"] = u["model"]
    return total


def generate_json(
    system_prompt: str,
    user_message: str,
    max_tokens: int = MAX_TOKENS,
    model: str | None = None,
) -> tuple[dict, dict]:
    """JSON 객체를 반환하는 범용 호출 (원천기사 발제 추천 등). 반환: (dict, usage)."""
    raw_text, usage = _call_claude(system_prompt, user_message, max_tokens, model)
    return _parse_json_object(raw_text), usage