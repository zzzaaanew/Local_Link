"""기자용 발제 서비스 MVP — FastAPI 백엔드.

실행: uvicorn main:app --reload
문서: http://localhost:8000/docs (자동 생성되는 API 테스트 화면)
"""
import os
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

import auth
import desk
import plan_doc
import press_pitches
import rewrite as rewrite_service
import rewrite_targets
import source_pitches
import stylebook
import suggestions as suggestion_store
import trends
import usage as usage_service
import weekly_schedule

app = FastAPI(title="발제 서비스 API", version="0.1.0")

# CORS
# - 고정 목록: 로컬 개발 + 운영 도메인
# - CORS_ORIGINS 환경변수(쉼표 구분)로 도메인을 추가할 수 있다
#
# 예전에는 allow_origin_regex=r"https://.*\.vercel\.app" 로 프리뷰 배포까지
# 한꺼번에 허용했다. 그런데 vercel.app 은 누구나 무료로 배포하는 공용 도메인이라,
# 사실상 "인터넷의 임의 페이지가 이 API를 호출 가능"과 같았다.
# 프리뷰 URL로 접속해야 할 때는 그 URL만 CORS_ORIGINS 에 넣는다.
_extra_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://l-link-frontend.vercel.app",
        "http://localhost:3000",
        "http://172.18.129.15:3000",
        "http://127.0.0.1:3000",
    ] + _extra_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------
# 요청 본문 스키마 (자동 검증)
# ------------------------------------------------------------

class VerifyRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100)


class ArticleRequest(BaseModel):
    session_id: str
    pitch_id: str | None = None
    article_url: str | None = None
    article_text: str | None = None


class RewriteRequest(BaseModel):
    source_type: str = Field(default="text", pattern="^(text|file)$")
    source_text: str = Field(min_length=50, description="보도자료·기사 본문 (최소 50자)")
    source_title: str = ""
    user_prompt: str | None = Field(default=None, max_length=1000)
    headline_count: int = Field(default=3, ge=1, le=5)


class PressPitchRequest(BaseModel):
    source_text: str = Field(min_length=50, description="보도자료 본문 (최소 50자)")
    source_title: str = ""
    user_prompt: str | None = Field(default=None, max_length=1000)
    count: int = Field(default=3, ge=1, le=6)


class PitchSelectRequest(BaseModel):
    pitch: dict
    session_id: str | None = None


class SuggestionPickRequest(BaseModel):
    suggestion_id: str


class DeskDraftRequest(BaseModel):
    pitch_id: str
    research_text: str = Field(min_length=20, max_length=20000)


class PlanSaveRequest(BaseModel):
    pitch: dict
    plan_markdown: str = Field(min_length=1)


class PlanDocRequest(BaseModel):
    pitch: dict
    format: str = Field(default="docx", pattern="^(docx|hwpx|pdf)$")


# ------------------------------------------------------------
# 엔드포인트
# ------------------------------------------------------------

@app.get("/api/health")
def health():
    """배포 확인용."""
    return {"status": "ok"}


@app.post("/api/auth/verify")
def verify(body: VerifyRequest):
    """접근 코드 검증 → 토큰 발급."""
    row = auth.verify_code(body.code)
    token = auth.issue_token(row)
    # owner_title이 비어 있으면 지금까지의 기본값 '기자'로 표기
    return {
        "token": token,
        "owner_name": row.get("owner_name"),
        "owner_title": row.get("owner_title") or "기자",
    }


@app.get("/api/usage")
def usage(payload: dict = Depends(auth.require_auth)):
    """오늘 사용량 / 일일 한도 조회 (표시용). {"used", "limit", "remaining"}"""
    return usage_service.get_daily(payload["access_code_id"])


@app.post("/api/articles")
def submit_article(body: ArticleRequest, payload: dict = Depends(auth.require_auth)):
    """완성 기사 등록 — '내가 선택한 발제'에서 출고 결과를 남긴다."""
    return desk.submit_article(
        access_code_id=payload["access_code_id"],
        session_id=body.session_id,
        pitch_id=body.pitch_id,
        article_url=body.article_url,
        article_text=body.article_text,
    )


# ============================================================
# 리라이팅 + 자사 스타일북
# ============================================================


@app.get("/api/stylebook")
def stylebook_rules(payload: dict = Depends(auth.require_auth)):
    """초안·리라이팅에 공통 적용되는 자사 스타일북 규칙."""
    return stylebook.summary()


@app.post("/api/rewrite")
def rewrite_article(body: RewriteRequest, payload: dict = Depends(auth.require_auth)):
    """보도자료·기사 리라이팅 → 본문 + 헤드라인 후보. (현재 텍스트 입력만 지원)"""
    if body.source_type != "text":
        raise HTTPException(
            status_code=400, detail="현재는 텍스트 입력만 지원합니다. (파일은 준비 중)"
        )
    code_id = payload["access_code_id"]
    usage_service.require_quota(code_id, "rewrite")
    return rewrite_service.rewrite_press_release(
        access_code_id=code_id,
        source_text=body.source_text,
        source_title=body.source_title,
        user_prompt=body.user_prompt,
        headline_count=body.headline_count,
    )


@app.get("/api/rewrite/targets")
def rewrite_target_list(
    count: int = 4,
    exclude: list[str] = Query(default=[]),
    payload: dict = Depends(auth.require_auth),
):
    """리라이팅 기사 후보. 연합뉴스 RSS(최근 24시간) → LLM 선별.

    exclude: 이전에 받은 기사 URL. '새로고침'에서 겹치지 않게 하려고 넘긴다.

    화면 진입 시 자동 실행은 전체 한도에서 빼지만, 이 기능만의 하루 상한
    (기본 5회)은 자동 실행분까지 포함해 적용한다. 기사 120건을 통째로 넣는
    호출이라 페이지를 반복해 열면 비용이 빠르게 늘기 때문이다.
    """
    code_id = payload["access_code_id"]
    is_refresh = bool(exclude)
    usage_service.require_quota(code_id, "rewrite_target", billable=is_refresh)
    try:
        result = rewrite_targets.list_rewrite_targets(
            code_id, count=count, excluded_urls=exclude
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"리라이팅 후보 생성 실패: {exc}") from exc

    usage_service.log(code_id, "rewrite_target", result.pop("usage", None), billable=is_refresh)
    suggestion_store.save_batch(code_id, "rewrite_target", result.get("targets", []))
    return result


# ============================================================
# 내가 선택한 발제(데스크): 초안 저장 + 목록 조회
# ============================================================

@app.post("/api/desk/select")
def desk_select(body: PitchSelectRequest, payload: dict = Depends(auth.require_auth)):
    """보도자료 발 발제에서 '이 아이템으로 시작' — 발제만 저장(초안 없음)."""
    code_id = payload["access_code_id"]
    result = desk.select_pitch(
        access_code_id=code_id, pitch=body.pitch, session_id=body.session_id
    )
    suggestion_store.mark_picked(
        code_id, body.pitch.get("suggestion_id"), result["pitch_id"]
    )
    return result


@app.post("/api/suggestions/pick")
def suggestion_pick(body: SuggestionPickRequest, payload: dict = Depends(auth.require_auth)):
    """추천물을 골랐다고 표시. 리라이팅 후보의 '이 기사로 쓰기'에서 호출한다."""
    suggestion_store.mark_picked(payload["access_code_id"], body.suggestion_id)
    return {"ok": True}


@app.get("/api/desk/item/{pitch_id}")
def desk_item(pitch_id: str, payload: dict = Depends(auth.require_auth)):
    """데스크 항목 하나 (발제 + 취재물 + 초안)."""
    return desk.get_item(payload["access_code_id"], pitch_id)


@app.post("/api/desk/draft")
def desk_draft(body: DeskDraftRequest, payload: dict = Depends(auth.require_auth)):
    """취재 내용 저장 + 기사 초안 생성. 취재 내용 없이는 호출할 수 없다."""
    code_id = payload["access_code_id"]
    usage_service.require_quota(code_id, "draft")
    return desk.add_research_and_draft(
        access_code_id=code_id,
        pitch_id=body.pitch_id,
        research_text=body.research_text,
    )


@app.post("/api/desk/save-plan")
def desk_save_plan(body: PlanSaveRequest, payload: dict = Depends(auth.require_auth)):
    """주간기획 취재 계획서를 '내가 선택한 발제'에 저장한다."""
    code_id = payload["access_code_id"]
    result = desk.save_plan(
        access_code_id=code_id, pitch=body.pitch, plan_markdown=body.plan_markdown
    )
    suggestion_store.mark_picked(
        code_id, body.pitch.get("suggestion_id"), result["pitch_id"]
    )
    return result


@app.get("/api/desk")
def desk_list(payload: dict = Depends(auth.require_auth)):
    """내가 선택한 발제 목록 (+취재물·초안·제출 기사)."""
    return {"items": desk.list_desk(payload["access_code_id"])}


# ============================================================
# 정부 주간일정: 서비스에 내장 (backend/data/government_schedule.txt)
# 갱신은 그 파일을 덮어쓰고 배포하면 된다 — 사용자 업로드는 없다.
# ============================================================

@app.get("/api/weekly-schedule")
def weekly_schedule_status(payload: dict = Depends(auth.require_auth)):
    """내장된 주간일정 정보 (부처 목록·글자수·갱신일)."""
    return weekly_schedule.get_status()


# ============================================================
# 홈: 주간기획 발제(정부 주간일정 기반) + 검색어 트렌드
# ============================================================

@app.get("/api/source-pitches/today")
def weekly_plan_pitches(
    count: int = 3,
    exclude: list[str] = Query(default=[]),
    payload: dict = Depends(auth.require_auth),
):
    """주간기획 발제.

    내장 정부 주간일정 → 경북 연결 일정 선별 → Neo4j 지식그래프 → 취재 계획서.
    exclude: 이전에 받은 제목들. '다시 만들기'에서 겹치지 않게 하려고 넘긴다.

    첫 접속은 화면에 들어가면 자동으로 도는 것이라 일일 한도에서 뺀다.
    exclude 가 붙어 오면 기자가 '새로고침'을 누른 것이므로 한도에 포함한다.
    """
    code_id = payload["access_code_id"]
    is_refresh = bool(exclude)
    if is_refresh:
        usage_service.require_quota(code_id, "plan")
    try:
        result = source_pitches.weekly_plans(count=count, excluded_titles=exclude)
    except HTTPException:
        raise  # 일정 파일 없음(503) 등은 그대로 전달
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"발제 생성 실패: {exc}") from exc

    usage_service.log(code_id, "plan", result.pop("usage", None), billable=is_refresh)
    # 생성된 제안서를 보관한다 (저장하지 않고 지나친 것도 남는다)
    suggestion_store.save_batch(code_id, "plan", result.get("pitches", []))
    return result


@app.post("/api/plan/document")
def plan_document(body: PlanDocRequest, payload: dict = Depends(auth.require_auth)):
    """취재 계획서를 문서 파일로 내려준다. format: docx | hwpx | pdf."""
    content, filename, media_type = plan_doc.build(body.pitch, body.format)
    quoted = quote(filename)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


@app.get("/api/trends")
def home_trends(
    period: str = "weekly",
    keywords: str = "",
    refresh: bool = False,
    payload: dict = Depends(auth.require_auth),
):
    """홈 우측 레일: 검색지수 순 키워드.

    period: daily(일간) | weekly(주간) | monthly(월간)
    keywords: 쉼표로 구분한 조회 키워드 (비우면 기본 풀)
    refresh=true면 캐시를 무시하고 다시 조회한다.
    """
    parsed = [k.strip() for k in keywords.split(",") if k.strip()]
    return trends.get_trends(
        payload["access_code_id"], period=period, keywords=parsed, force=refresh
    )


@app.post("/api/press-pitches")
def press_pitch_generate(body: PressPitchRequest, payload: dict = Depends(auth.require_auth)):
    """보도자료 발 발제: 보도자료 → 엔티티 추출 → 지식그래프 → 발제 후보."""
    code_id = payload["access_code_id"]
    usage_service.require_quota(code_id, "press_pitch")
    try:
        result = press_pitches.generate(
            source_text=body.source_text, user_prompt=body.user_prompt, count=body.count
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"발제 후보 생성 실패: {exc}") from exc

    usage_service.log(code_id, "press_pitch", result.pop("usage", None))

    # 입력한 보도자료 원문을 여기서 저장한다. 발제만 뽑아보고 아무것도 고르지
    # 않아도 원문이 남아야 나중에 무엇을 넣었는지 확인할 수 있다.
    session_id = suggestion_store.create_source_session(
        code_id, body.source_title, body.source_text
    )
    suggestion_store.save_batch(
        code_id, "press_pitch", result.get("pitches", []), session_id=session_id
    )
    result["session_id"] = session_id
    return result
