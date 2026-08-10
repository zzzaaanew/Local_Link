"""스타일북 — 자사 기사 작성 규칙. 초안·리라이팅 두 기능이 함께 쓴다.

규칙은 `backend/data/stylebook.json` 에 들어 있고, 서비스에 내장되어 모든
사용자에게 동일하게 적용된다. 규칙을 바꾸려면 그 파일만 고치고 배포하면 된다
(코드 수정·DB 작업·서버 재시작 없음).

rewrite.txt 프롬프트가 "스타일북과 본 프롬프트가 충돌하면 스타일북을 우선
적용한다"고 지시하므로, 여기서 만든 블록이 사실상 최상위 규칙이 된다.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STYLEBOOK_PATH = Path(__file__).parent / "data" / "stylebook.json"


def load() -> dict:
    """스타일북 원본. 파일이 없거나 깨져도 기능을 막지는 않는다(규칙 없이 진행)."""
    if not STYLEBOOK_PATH.exists():
        logger.warning("스타일북 파일 없음: %s", STYLEBOOK_PATH)
        return {"rules": []}
    try:
        data = json.loads(STYLEBOOK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("스타일북을 읽지 못했습니다: %s", exc)
        return {"rules": []}

    rules = data.get("rules")
    if not isinstance(rules, list):
        return {"rules": []}
    return data


def as_prompt_block() -> str:
    """프롬프트에 넣을 스타일북 블록. 규칙이 없으면 빈 문자열.

    분류(category)별로 묶고 O/X 예시를 함께 넣는다. 표기준칙은 설명만으로는
    모호한 규칙이 많아(띄어쓰기·약물 위치 등) 예시가 있어야 정확히 지켜진다.
    """
    data = load()
    rules = [r for r in data.get("rules", []) if isinstance(r, dict) and r.get("instruction")]
    if not rules:
        return ""

    lines = [f"[자사 스타일북 — 최우선 적용] {data.get('name', '')}".rstrip()]

    grouped: dict[str, list[dict]] = {}
    for rule in rules:
        grouped.setdefault(rule.get("category") or "기타", []).append(rule)

    for category, items in grouped.items():
        # 분류 머리글에 ◇△ 를 쓰지 않는다. 표기준칙이 그 약물에 기사 본문용
        # 의미를 부여하고 있어서, 모델이 프롬프트 구조를 기사에 그대로 흉내 낼 수 있다.
        lines.append(f"# {category}")
        for rule in items:
            lines.append(f"- {rule.get('name') or rule.get('id') or ''}: {rule['instruction']}")
            examples = rule.get("examples") or {}
            good, bad = examples.get("good"), examples.get("bad")
            if good:
                lines.append(f"  O: {good}")
            if bad:
                lines.append(f"  X: {bad}")

    lines.append("위 규칙이 다른 지시와 충돌하면 스타일북을 따른다.")
    return "\n".join(lines)


def summary() -> dict:
    """화면 표시용 요약."""
    data = load()
    rules = [r for r in data.get("rules", []) if isinstance(r, dict)]
    return {
        "available": bool(rules),
        "name": data.get("name") or "스타일북",
        "version": data.get("version"),
        "count": len(rules),
        "rules": [
            {
                "id": r.get("id"),
                "category": r.get("category"),
                "name": r.get("name"),
                "instruction": r.get("instruction"),
                "examples": r.get("examples") or {},
            }
            for r in rules
        ],
    }
