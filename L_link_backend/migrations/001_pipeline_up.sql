-- ============================================================
-- 작업 A: 파이프라인 2종 구조화 (경량형/심층형) — 적용(up)
-- 실행: Supabase 대시보드 → SQL Editor → 붙여넣기 → Run
-- 되돌리기: 001_pipeline_down.sql
--
-- ※ 실행 전 제약 이름 1회 확인(표준 자동명을 전제로 함):
--   select conname from pg_constraint
--   where conrelid in ('pitches'::regclass,'usage_logs'::regclass);
-- ============================================================
begin;

-- 1) pitches: 파이프라인 타입 + 상태 확장 (기존 shown/selected/rejected 유지)
alter table pitches add column if not exists pipeline_type text
  check (pipeline_type in ('lightweight','deep'));      -- null = 아직 미선택

alter table pitches drop constraint if exists pitches_status_check;
alter table pitches add constraint pitches_status_check check (status in (
  'shown','selected','rejected',
  'drafting','draft_completed','researching','research_completed'));

-- 2) 취재물 (심층형 전용)
create table if not exists research_notes (
  id         uuid primary key default gen_random_uuid(),
  pitch_id   uuid not null references pitches(id),
  content    text not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_research_notes_pitch on research_notes(pitch_id);

-- 3) 초안/리라이팅 결과 통합 테이블 (작업 A·B 공용)
create table if not exists drafts (
  id               uuid primary key default gen_random_uuid(),
  session_id       uuid not null references sessions(id),
  pitch_id         uuid references pitches(id),         -- 리라이팅 시 null
  kind             text not null
                     check (kind in ('draft_lightweight','draft_deep','rewrite')),
  tone_profile_id  uuid,                                -- FK는 002에서 연결 (작업 B)
  length           text check (length in ('단신','중간','심층')),
  headline_count   int,
  body_text        text not null,
  headlines        jsonb not null default '[]',
  status           text not null default 'generated'
                     check (status in ('generated','approved','rejected')),
  version          int  not null default 1,
  model            text,
  input_tokens     int,
  output_tokens    int,
  created_at       timestamptz not null default now()
);
create index if not exists idx_drafts_session on drafts(session_id);
create index if not exists idx_drafts_pitch on drafts(pitch_id);

-- 4) 상태 전이 이력
create table if not exists pitch_status_history (
  id          uuid primary key default gen_random_uuid(),
  pitch_id    uuid not null references pitches(id),
  from_status text,
  to_status   text not null,
  created_at  timestamptz not null default now()
);
create index if not exists idx_psh_pitch on pitch_status_history(pitch_id);

-- 5) usage_logs.action 확장 (초안/리라이팅/톤요약 비용 추적)
alter table usage_logs drop constraint if exists usage_logs_action_check;
alter table usage_logs add constraint usage_logs_action_check
  check (action in ('generate','refresh','draft','rewrite','tone_summary'));

-- RLS: 기존 테이블과 동일 정책(켜되 정책 없음 → service_role만 접근)
alter table research_notes       enable row level security;
alter table drafts               enable row level security;
alter table pitch_status_history enable row level security;

-- 6) 관리자 뷰: 일일 사용량도 생성·새로고침만 카운트 (enforcement와 일치)
create or replace view v_daily_usage as
select
  ac.code, ac.owner_name, ac.daily_limit,
  count(ul.id) as used_today,
  ac.daily_limit - count(ul.id) as remaining
from access_codes ac
left join usage_logs ul
  on ul.access_code_id = ac.id
 and ul.created_at >= date_trunc('day', now())
 and ul.action in ('generate','refresh')
group by ac.id, ac.code, ac.owner_name, ac.daily_limit;

commit;
