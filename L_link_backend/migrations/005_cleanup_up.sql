-- ============================================================
-- DB 정리 — 적용(up)
-- 선행: 001~004
-- 되돌리기: 005_cleanup_down.sql  (※ 삭제한 테이블의 데이터는 복구되지 않음)
--
-- 하는 일
--   1. 죽은 테이블 2개 삭제  (tone_profiles, pitch_status_history)
--   2. 죽은 컬럼 9개 삭제
--   3. 실제로 쓰는 값만 남도록 CHECK 제약 정리
--   4. sessions.source_text 를 NULL 허용으로 (취재 제안서는 원문이 없다)
--   5. 사용량 로그 재설계 (모든 LLM 호출 기록 + 한도 대상 구분)
--   6. 관리자 뷰 교체 — 이름으로 누가 무엇을 했는지 조회
--
-- 여러 번 실행해도 안전합니다(멱등).
-- ============================================================
begin;

-- ------------------------------------------------------------
-- 0) 옛 뷰 제거 (컬럼을 지우려면 뷰를 먼저 없애야 한다)
--
--    Postgres 는 뷰가 참조하는 컬럼을 지우지 못하게 막는다
--    ("cannot drop column ... because other objects depend on it").
--    Supabase 대시보드에서 직접 만든 뷰까지 있을 수 있어, 이름을 일일이
--    적는 대신 **대상 테이블에 의존하는 public 뷰를 전부 찾아 제거**한다.
--
--    ※ 실행 전에 아래 질의로 기존 뷰 정의를 백업해 두세요.
--      select table_name, view_definition
--      from information_schema.views where table_schema = 'public';
--
--    우리 뷰(v_작업목록 등)는 006/008 에서 다시 만들어집니다.
-- ------------------------------------------------------------
do $$
declare
  v record;
begin
  for v in
    select distinct c.relname as view_name
    from pg_depend d
    join pg_rewrite r      on r.oid = d.objid
    join pg_class   c      on c.oid = r.ev_class
    join pg_namespace n    on n.oid = c.relnamespace
    join pg_class   src    on src.oid = d.refobjid
    where c.relkind = 'v'
      and n.nspname = 'public'
      and src.relname in (
        'pitches', 'sessions', 'drafts', 'usage_logs',
        'access_codes', 'research_notes', 'articles'
      )
  loop
    execute format('drop view if exists public.%I cascade', v.view_name);
    raise notice '제거한 뷰: %', v.view_name;
  end loop;
end $$;

-- ------------------------------------------------------------
-- 1) 죽은 테이블
-- ------------------------------------------------------------
-- 톤 프로파일: 기능 제거로 더 이상 쓰지 않는다 (스타일북이 대체)
alter table drafts drop constraint if exists drafts_tone_profile_fk;
drop table if exists tone_profiles;

-- 상태 이력: 기록만 하고 읽는 곳이 없었다.
-- 진행 상황은 pitches.status + drafts.created_at 으로 충분히 보인다.
drop table if exists pitch_status_history;

-- ------------------------------------------------------------
-- 2) 죽은 컬럼
-- ------------------------------------------------------------
alter table drafts   drop column if exists tone_profile_id;  -- 톤 프로파일 제거
alter table drafts   drop column if exists length;           -- 단신/리라이팅 모드 제거
alter table drafts   drop column if exists status;           -- 승인 흐름 미구현
alter table drafts   drop column if exists version;          -- 버전 관리 미구현

alter table pitches  drop column if exists feasibility_score; -- 한 번도 채운 적 없음
alter table pitches  drop column if exists generation_round;  -- 항상 1
alter table pitches  drop column if exists pipeline_type;     -- 취재 필수로 통일되며 무의미

alter table sessions drop column if exists source_type;      -- 항상 'text'
alter table sessions drop column if exists source_url;       -- URL 입력 미지원

-- ------------------------------------------------------------
-- 3) 옛 CHECK 제약을 먼저 푼다
--
--    순서가 중요하다. 제약이 걸린 채로 새 값을 UPDATE 하면 그 UPDATE 자체가
--    옛 제약에 막힌다("violated by some row"). 풀고 → 옮기고 → 다시 건다.
-- ------------------------------------------------------------
alter table pitches    drop constraint if exists pitches_status_check;
alter table sessions   drop constraint if exists sessions_article_kind_check;
alter table drafts     drop constraint if exists drafts_kind_check;
alter table usage_logs drop constraint if exists usage_logs_action_check;

-- ------------------------------------------------------------
-- 4) 기존 데이터를 새 값으로 옮긴다 (행을 지우지 않는다)
--
--    구버전(/main 화면) 시절 값이 그대로 남아 있다. 뜻이 가장 가까운
--    새 값으로 바꾼다.
-- ------------------------------------------------------------

-- 발제 상태
--   shown / rejected : 생성만 되고 기자가 고르지 않은 것 → archived(보관)
--   진행 중이던 상태  : 취재 대기와 같은 자리          → selected
update pitches set status = 'archived'
  where status in ('shown', 'rejected');
update pitches set status = 'selected'
  where status in ('drafting', 'researching', 'research_completed');

-- 세션 종류: 구버전 daily/feature 는 모두 보도자료에서 출발한 작업이었다
update sessions set article_kind = 'press'
  where article_kind in ('daily', 'feature');

-- 산출물: 취재 없이 만들던 경량 초안은 이제 없다 → 초안으로 통합
-- (취재를 했는지는 research_notes 유무로 여전히 구분된다)
update drafts set kind = 'draft_deep'
  where kind = 'draft_lightweight';

-- 사용량 로그: 구버전 generate/refresh 는 보도자료 발제 생성이었다
update usage_logs set action = 'press_pitch'
  where action in ('generate', 'refresh');
-- 톤 프로파일 요약은 대응되는 기능이 사라졌다 (보통 0건)
delete from usage_logs where action = 'tone_summary';

-- 혹시 모를 나머지 값 정리 (위 매핑에 없는 값이 있었다면)
update pitches    set status = 'archived'
  where status not in ('selected','draft_completed','archived');
update sessions   set article_kind = 'press'
  where article_kind not in ('press','source','rewrite');
update drafts     set kind = 'draft_deep'
  where kind not in ('plan','draft_deep','rewrite');
delete from usage_logs
  where action not in ('plan','press_pitch','rewrite_target','rewrite','draft');

-- ------------------------------------------------------------
-- 5) 새 CHECK 제약 — 코드가 실제로 쓰는 값만
-- ------------------------------------------------------------
-- 발제 상태
--   selected         취재 대기
--   draft_completed  초안 완료
--   archived         구버전에서 넘어온 미선택 발제 (화면·뷰에는 나오지 않음)
alter table pitches add constraint pitches_status_check
  check (status in ('selected','draft_completed','archived'));

-- 세션 종류: 무엇에서 출발한 작업인지
--   press   보도자료 발 발제
--   source  주간기획 취재 제안서 (원문 없음)
--   rewrite 리라이팅
alter table sessions add constraint sessions_article_kind_check
  check (article_kind in ('press','source','rewrite'));
alter table sessions alter column article_kind drop default;

-- 산출물 종류
--   plan        취재 제안서 (주간기획)
--   draft_deep  취재 반영 기사 초안
--   rewrite     리라이팅 본문
alter table drafts add constraint drafts_kind_check
  check (kind in ('plan','draft_deep','rewrite'));

-- ------------------------------------------------------------
-- 6) 취재 제안서는 원문이 없다 → 가짜 원문을 넣지 않도록 NULL 허용
-- ------------------------------------------------------------
alter table sessions alter column source_text drop not null;

-- ------------------------------------------------------------
-- 7) 사용량 로그 재설계
--    이전 구조는 'generate','refresh' 만 세었는데 그 액션을 쓰는 코드가
--    사라져 집계가 항상 0이었다. 이제 모든 LLM 호출을 기록한다.
--
--    billable = true  기자가 버튼을 눌러 일어난 생성 → 일일 한도에 포함
--    billable = false 화면에 들어가면 자동 실행 → 비용은 기록하되 한도에서 제외
-- ------------------------------------------------------------
alter table usage_logs add column if not exists billable boolean not null default true;

alter table usage_logs add constraint usage_logs_action_check check (action in (
  'plan',            -- 오늘의 발제 추천 (취재 계획서)
  'press_pitch',     -- 보도자료 발 발제
  'rewrite_target',  -- 리라이팅 기사 후보 발굴
  'rewrite',         -- 리라이팅 본문
  'draft'            -- 취재 반영 기사 초안
));

create index if not exists idx_usage_billable
  on usage_logs(access_code_id, billable, created_at desc);

-- 월 단위 비용 상한(선택). null 이면 제한 없음.
alter table access_codes add column if not exists monthly_token_limit bigint;

commit;
