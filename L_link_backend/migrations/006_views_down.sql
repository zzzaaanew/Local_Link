-- ============================================================
-- 006 롤백. 뷰만 제거한다 (테이블·데이터에는 영향 없음).
-- ============================================================
begin;

drop view if exists v_작업목록;
drop view if exists v_출고기사;
drop view if exists v_기자별_현황;
drop view if exists v_사용량_오늘;
drop view if exists v_사용량_월간;

commit;
