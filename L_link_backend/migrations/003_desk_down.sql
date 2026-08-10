-- ============================================================
-- 003 롤백. 주의: article_kind='source' 세션이 있으면 먼저 정리해야 한다.
-- ============================================================
begin;

alter table sessions drop constraint if exists sessions_article_kind_check;
alter table sessions add constraint sessions_article_kind_check
  check (article_kind in ('daily','feature','rewrite'));

commit;
