-- ============================================================
-- 작업 B 롤백(down). 002_rewrite_up.sql 을 되돌린다.
-- (001 롤백보다 먼저 실행할 것 — drafts FK가 tone_profiles를 참조하므로)
-- ============================================================
begin;

alter table sessions drop constraint if exists sessions_article_kind_check;
alter table sessions add constraint sessions_article_kind_check
  check (article_kind in ('daily','feature'));

alter table drafts drop constraint if exists drafts_tone_profile_fk;

drop table if exists tone_profiles;

commit;
