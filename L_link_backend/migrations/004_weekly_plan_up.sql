-- ============================================================
-- 주간기획 취재 제안서 + 보도자료 발 발제(취재 필수) — 적용(up)
-- 선행: 001~003
-- 되돌리기: 004_weekly_plan_down.sql
--
-- 여러 번 실행해도 안전합니다(멱등).
-- ※ 이전 버전의 004(weekly_schedules 테이블 생성)를 이미 실행하셨다면
--    이 파일을 다시 실행하면 그 테이블이 정리됩니다.
--    정부 주간일정은 이제 DB가 아니라 backend/data/government_schedule.txt 에
--    내장되어 모든 사용자가 공유합니다.
-- ============================================================
begin;

-- 1) 사용하지 않게 된 주간일정 테이블 정리 (없으면 그냥 통과)
drop table if exists weekly_schedules;

-- 2) drafts.kind 에 'plan' 추가 (취재 계획서 저장용)
--    취재→초안 흐름 대신 계획서 자체를 저장하므로 별도 테이블을 만들지 않는다.
alter table drafts drop constraint if exists drafts_kind_check;
alter table drafts add constraint drafts_kind_check
  check (kind in ('draft_lightweight','draft_deep','rewrite','plan'));

-- 3) sessions.article_kind 에 'press' 추가
--    보도자료 발 발제로 선택한 발제의 원문 컨테이너 (취재 후 초안 생성에 사용)
alter table sessions drop constraint if exists sessions_article_kind_check;
alter table sessions add constraint sessions_article_kind_check
  check (article_kind in ('daily','feature','rewrite','source','press'));

commit;
