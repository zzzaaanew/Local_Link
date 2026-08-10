-- ============================================================
-- 원천기사 발제 저장('내가 선택한 발제') — 적용(up)
-- 선행: 001_pipeline_up.sql, 002_rewrite_up.sql
-- 되돌리기: 003_desk_down.sql
-- ============================================================
begin;

-- 보도자료 원문이 없는 '원천기사 발제'를 세션으로 보관하기 위해 'source' 추가
alter table sessions drop constraint if exists sessions_article_kind_check;
alter table sessions add constraint sessions_article_kind_check
  check (article_kind in ('daily','feature','rewrite','source'));

commit;
