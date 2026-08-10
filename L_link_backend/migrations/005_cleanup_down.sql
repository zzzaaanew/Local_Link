-- ============================================================
-- 005 롤백.
-- 주의: 삭제한 테이블(tone_profiles, pitch_status_history)의 데이터와
--       삭제한 컬럼의 값은 복구되지 않습니다. 구조만 되돌립니다.
-- ============================================================
begin;

drop view if exists v_작업목록;
drop view if exists v_출고기사;
drop view if exists v_기자별_현황;
drop view if exists v_사용량_오늘;
drop view if exists v_사용량_월간;

-- 컬럼 되살리기 (값은 비어 있음)
alter table drafts   add column if not exists tone_profile_id uuid;
alter table drafts   add column if not exists length text;
alter table drafts   add column if not exists status text not null default 'generated';
alter table drafts   add column if not exists version int not null default 1;
alter table pitches  add column if not exists feasibility_score int;
alter table pitches  add column if not exists generation_round int not null default 1;
alter table pitches  add column if not exists pipeline_type text;
alter table sessions add column if not exists source_type text not null default 'text';
alter table sessions add column if not exists source_url text;

-- 제약 되돌리기.
-- 005 가 옮겨 놓은 값(archived 등)이 그대로 남아 있으므로, 옛 값과 새 값을
-- 모두 허용하는 합집합으로 건다. 그러지 않으면 롤백 자체가 실패한다.
alter table pitches drop constraint if exists pitches_status_check;
alter table pitches add constraint pitches_status_check check (status in (
  'shown','selected','rejected','archived',
  'drafting','draft_completed','researching','research_completed'));

alter table sessions drop constraint if exists sessions_article_kind_check;
alter table sessions add constraint sessions_article_kind_check
  check (article_kind in ('daily','feature','rewrite','source','press'));
alter table sessions alter column article_kind set default 'feature';

alter table drafts drop constraint if exists drafts_kind_check;
alter table drafts add constraint drafts_kind_check
  check (kind in ('draft_lightweight','draft_deep','rewrite','plan'));

-- source_text 는 NOT NULL 로 되돌리기 전에 빈 값을 채워야 한다
update sessions set source_text = '' where source_text is null;
alter table sessions alter column source_text set not null;

alter table usage_logs drop constraint if exists usage_logs_action_check;
alter table usage_logs add constraint usage_logs_action_check
  check (action in ('generate','refresh','draft','rewrite','tone_summary',
                    'plan','press_pitch','rewrite_target'));
alter table usage_logs drop column if exists billable;

alter table access_codes drop column if exists monthly_token_limit;

-- 상태 이력 테이블 재생성 (빈 상태)
create table if not exists pitch_status_history (
  id          uuid primary key default gen_random_uuid(),
  pitch_id    uuid not null references pitches(id),
  from_status text,
  to_status   text not null,
  created_at  timestamptz not null default now()
);
alter table pitch_status_history enable row level security;

create or replace view v_daily_usage as
select
  ac.code, ac.owner_name, ac.daily_limit,
  count(ul.id) as used_today,
  ac.daily_limit - count(ul.id) as remaining
from access_codes ac
left join usage_logs ul
  on ul.access_code_id = ac.id
 and ul.created_at >= date_trunc('day', now())
group by ac.id, ac.code, ac.owner_name, ac.daily_limit;

commit;
