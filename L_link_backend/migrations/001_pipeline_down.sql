-- ============================================================
-- 작업 A 롤백(down). 001_pipeline_up.sql 을 되돌린다.
-- ============================================================
begin;

drop table if exists pitch_status_history;
drop table if exists drafts;
drop table if exists research_notes;

alter table usage_logs drop constraint if exists usage_logs_action_check;
alter table usage_logs add constraint usage_logs_action_check
  check (action in ('generate','refresh'));

-- 주의: 아래 status 축소 전, 새 상태값(drafting/draft_completed/researching/
-- research_completed)을 가진 pitches 행이 있으면 먼저 정리해야 제약 추가가 성공한다.
alter table pitches drop constraint if exists pitches_status_check;
alter table pitches add constraint pitches_status_check
  check (status in ('shown','selected','rejected'));

alter table pitches drop column if exists pipeline_type;

-- 관리자 뷰 원복 (action 필터 제거)
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
