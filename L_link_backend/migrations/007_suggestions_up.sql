-- ============================================================
-- 추천물 보관 — 적용(up)
-- 선행: 005, 006
-- 되돌리기: 007_suggestions_down.sql
--
-- 지금까지는 기자가 '선택한' 것만 남고, AI가 무엇을 추천했는지는 사라졌다.
-- 그래서 "무엇을 보여줬는데 무엇을 골랐나"를 볼 수 없었다.
-- 이제 생성 시점에 전부 저장하고, 고른 것에 표시를 남긴다.
--
-- 저장되는 것
--   · 오늘의 발제 취재 제안서 (3건)
--   · 보도자료 발 발제 후보   (3건)
--   · 리라이팅 후보 기사      (4건)
--   · 입력한 보도자료 원문    (sessions — 생성 시점에 저장)
--
-- 여러 번 실행해도 안전합니다(멱등).
-- ============================================================
begin;

-- ------------------------------------------------------------
-- 1) 추천물 — 세 기능이 한 테이블을 공유한다 (테이블 난립 방지)
-- ------------------------------------------------------------
create table if not exists suggestions (
  id             uuid primary key default gen_random_uuid(),
  access_code_id uuid not null references access_codes(id),
  session_id     uuid references sessions(id),   -- 보도자료 발제일 때 원문 세션

  kind           text not null check (kind in (
                   'plan',            -- 오늘의 발제 취재 제안서
                   'press_pitch',     -- 보도자료 발 발제 후보
                   'rewrite_target'   -- 리라이팅 후보 기사
                 )),
  batch_id       uuid not null,       -- 한 번의 생성으로 함께 나온 묶음
  position       int  not null,       -- 묶음 안 순서 (1부터)

  title          text not null,
  summary        text,
  why            text,                -- 추천 이유 / 지역 앵글
  body           text,                -- 제안서 전문(plan) — 다른 종류는 비움

  org            text,                -- 관련 기관 / 언론사
  region         text,
  timing         text,                -- 사전 준비형 · 당일 대응형
  scheduled_at   text,                -- 발표 예정일 / 기사 발행일시
  url            text,                -- 리라이팅 후보 원문 링크

  picked         boolean not null default false,  -- 기자가 골랐는가
  picked_at      timestamptz,
  pitch_id       uuid references pitches(id),     -- 고른 뒤 만들어진 발제
  created_at     timestamptz not null default now()
);

create index if not exists idx_suggestions_code
  on suggestions(access_code_id, created_at desc);
create index if not exists idx_suggestions_batch on suggestions(batch_id);
create index if not exists idx_suggestions_picked
  on suggestions(picked, created_at desc);

alter table suggestions enable row level security;

-- ------------------------------------------------------------
-- 2) 보도자료 원문을 생성 시점에 저장한다
--    지금까지는 기자가 '이 아이템으로 시작'을 눌러야만 세션이 만들어져,
--    발제만 뽑아보고 고르지 않으면 입력한 원문이 사라졌다.
--    → sessions 를 발제 생성 시점에 만들고, 선택 시 그 세션을 재사용한다.
--    (구조 변경 없음. 코드 동작만 바뀌므로 여기서는 주석으로만 남긴다.)
-- ------------------------------------------------------------

commit;
