"""정부 주간일정 — 서비스에 내장된 일정 파일을 모든 사용자에게 공급한다.

주간기획 발제는 '아직 일어나지 않은 정부 일정'을 근거로 삼는다. 그 일정 텍스트는
`backend/data/government_schedule.txt` 에 들어 있고, 기자별 업로드 없이
모든 사용자가 같은 파일을 사용한다.

일정을 갱신하려면 그 파일만 새 내용으로 덮어쓰고 배포하면 된다
(코드 수정·DB 작업·서버 재시작 모두 필요 없다).
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

logger = logging.getLogger(__name__)

SCHEDULE_PATH = Path(__file__).parent / "data" / "government_schedule.txt"
MAX_CHARS = 40000  # 프롬프트에 넣을 상한 (토큰 통제)


def load() -> str:
    """내장 일정 본문. 파일이 없거나 비어 있으면 안내와 함께 거부한다."""
    if not SCHEDULE_PATH.exists():
        logger.error("정부 주간일정 파일 없음: %s", SCHEDULE_PATH)
        raise HTTPException(
            status_code=503,
            detail="정부 주간일정 파일이 서버에 없습니다. 관리자에게 문의해주세요.",
        )

    text = _read().strip()
    if len(text) < 50:
        raise HTTPException(
            status_code=503,
            detail="정부 주간일정 파일이 비어 있습니다. 관리자에게 문의해주세요.",
        )
    return text[:MAX_CHARS]


def get_status() -> dict:
    """화면 표시용 메타 정보. 본문은 미리보기만 준다."""
    if not SCHEDULE_PATH.exists():
        return {"available": False}

    text = _read()
    stat = SCHEDULE_PATH.stat()
    return {
        "available": len(text.strip()) >= 50,
        "filename": SCHEDULE_PATH.name,
        "chars": len(text),
        "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "agencies": _agencies(text),
        "preview": text.strip()[:400],
    }


def _read() -> str:
    """한국어 텍스트 파일은 UTF-8 또는 CP949로 저장되는 경우가 많다."""
    raw = SCHEDULE_PATH.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _agencies(text: str) -> list[str]:
    """일정 파일에 담긴 부처 목록. '◇재정경제부' 형태의 머리글을 모은다."""
    names = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("◇") and len(line) > 1:
            name = line[1:].strip()
            if name and name not in names:
                names.append(name)
    return names
