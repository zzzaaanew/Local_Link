"""접근 코드 인증 + 일일 사용량 통제.

흐름:
1) POST /api/auth/verify 에서 코드를 검증하고 JWT 토큰을 발급
2) 이후 모든 API는 require_auth 의존성이 토큰을 검증
3) 생성 계열 API는 usage.require_quota 로 일일 한도를 확인

사용량 집계·한도는 usage.py 로 옮겼다 (인증과 과금은 관심사가 다르다).
"""
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db import supabase

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
TOKEN_HOURS = 24  # 토큰 유효 시간

bearer = HTTPBearer(auto_error=False)


def verify_code(code: str) -> dict:
    """접근 코드를 DB와 대조. 유효하면 access_codes 행을 반환."""
    res = (
        supabase.table("access_codes")
        .select("*")
        .eq("code", code.strip())
        .eq("is_active", True)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=401, detail="유효하지 않거나 비활성화된 코드입니다.")
    return res.data[0]


def issue_token(access_code_row: dict) -> str:
    """검증된 코드에 대해 JWT 발급. payload에 코드 id를 담는다."""
    payload = {
        "access_code_id": access_code_row["id"],
        "code": access_code_row["code"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """모든 보호 API 앞에 붙는 의존성. 토큰을 검증하고 payload를 반환."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다. 코드를 다시 입력하세요.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    return payload
