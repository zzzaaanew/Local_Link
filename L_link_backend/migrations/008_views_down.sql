-- ============================================================
-- 008 롤백. 뷰만 제거한다 (테이블·데이터에는 영향 없음).
-- 006 의 뷰까지 함께 사라지므로, 되돌린 뒤 006_views_up.sql 을 다시
-- 실행하면 이전 상태(뷰 5개)로 돌아갑니다.
-- ============================================================
begin;

drop view if exists v_작업목록;
drop view if exists v_출고기사;
drop view if exists v_입력자료;
drop view if exists v_취재물;
drop view if exists v_추천내역;
drop view if exists v_제안서보관;
drop view if exists v_기자별_현황;
drop view if exists v_사용량_오늘;
drop view if exists v_사용량_월간;

commit;
