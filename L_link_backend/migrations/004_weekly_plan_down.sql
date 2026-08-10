-- ============================================================
-- 004 롤백.
-- 주의: kind='plan' 인 drafts, article_kind='press' 인 sessions 가 있으면
--       먼저 정리해야 제약조건이 다시 걸립니다.
-- ============================================================
begin;

alter table drafts drop constraint if exists drafts_kind_check;
alter table drafts add constraint drafts_kind_check
  check (kind in ('draft_lightweight','draft_deep','rewrite'));

alter table sessions drop constraint if exists sessions_article_kind_check;
alter table sessions add constraint sessions_article_kind_check
  check (article_kind in ('daily','feature','rewrite','source'));

commit;
