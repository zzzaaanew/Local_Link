-- ============================================================
-- 작업 B: 리라이팅 + 자사 톤 프로파일 — 적용(up)
-- 선행: 001_pipeline_up.sql (drafts 테이블 필요)
-- 되돌리기: 002_rewrite_down.sql
--
-- ※ 실행 전 제약 이름 1회 확인:
--   select conname from pg_constraint where conrelid = 'sessions'::regclass;
-- ============================================================
begin;

-- 1) 자사 톤 프로파일 (버전 이력 보존: 재학습 시 새 행 + is_active 전환)
create table if not exists tone_profiles (
  id                 uuid primary key default gen_random_uuid(),
  access_code_id     uuid not null references access_codes(id),
  newspaper_name     text not null,
  slogan             text,
  honorific_style    text,                        -- 예: "A씨(전통 보도형)"
  banned_expressions jsonb not null default '[]', -- 금지 표현 목록
  sample_articles    jsonb not null default '[]', -- 대표 과거 기사 ≤5건
  summary            jsonb,                        -- LLM 생성 요약(구조화)
  version            int  not null default 1,
  is_active          boolean not null default true,
  created_at         timestamptz not null default now()
);
create index if not exists idx_tone_profiles_code on tone_profiles(access_code_id);

-- 2) drafts.tone_profile_id → tone_profiles FK 연결
alter table drafts drop constraint if exists drafts_tone_profile_fk;
alter table drafts add constraint drafts_tone_profile_fk
  foreign key (tone_profile_id) references tone_profiles(id);

-- 3) sessions.article_kind 에 'rewrite' 추가 (원문 컨테이너 재사용)
alter table sessions drop constraint if exists sessions_article_kind_check;
alter table sessions add constraint sessions_article_kind_check
  check (article_kind in ('daily','feature','rewrite'));

alter table tone_profiles enable row level security;

commit;
