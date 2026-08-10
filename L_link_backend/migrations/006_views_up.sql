-- ============================================================
-- ⚠️ 이 파일은 008_views_up.sql 로 대체되었습니다. 실행하지 마세요.
--    008 이 여기 뷰 5개를 모두 포함하고 4개를 더합니다.
--    005 → 007 → 008 순서로만 실행하면 됩니다.
--    (기록을 위해 남겨 둡니다.)
-- ============================================================
-- 관리자 조회용 뷰 — 적용(up)
-- 선행: 005_cleanup_up.sql
-- 되돌리기: 006_views_down.sql
--
-- Supabase 대시보드 → Table Editor 왼쪽 목록에서 바로 열어 볼 수 있습니다.
-- 컬럼명을 한글로 둔 이유는 조인 없이 그대로 읽히게 하기 위해서입니다.
--
--   v_기자별_현황   누가 무엇을 몇 건 만들었나 (한 줄 = 기자 1명)
--   v_작업목록      누가 어떤 발제를 선택했나 (한 줄 = 작업 1건)  ★ 주력
--   v_출고기사      누가 어떤 기사를 썼나
--   v_사용량_오늘   오늘 사용량과 남은 횟수
--   v_사용량_월간   기자별 월간 호출/토큰
-- ============================================================
begin;

-- ------------------------------------------------------------
-- 1) 작업 목록 — 가장 자주 볼 화면
--    "누가 어떤 발제를 선택했고 어디까지 갔는가"
-- ------------------------------------------------------------
create or replace view v_작업목록 as
select
  ac.owner_name                                   as 기자,
  ac.owner_org                                    as 소속,
  case s.article_kind
    when 'source'  then '취재 제안서'
    when 'press'   then '보도자료 발제'
    when 'rewrite' then '리라이팅'
  end                                             as 종류,
  p.title                                         as 제목,
  case
    when a.id is not null then '기사 출고'
    when d.id is not null then '초안 완료'
    else                       '취재 대기'
  end                                             as 진행,
  coalesce(n.cnt, 0)                              as 취재물,
  a.article_url                                   as 기사링크,
  (p.created_at at time zone 'Asia/Seoul')        as 선택일시,
  p.id                                            as pitch_id
from pitches p
join sessions s      on s.id = p.session_id
join access_codes ac on ac.id = s.access_code_id
-- 발제당 최신 산출물 1건
left join lateral (
  select d.id, d.kind
  from drafts d
  where d.pitch_id = p.id
  order by d.created_at desc
  limit 1
) d on true
left join lateral (
  select a.id, a.article_url
  from articles a
  where a.pitch_id = p.id
  order by a.submitted_at desc
  limit 1
) a on true
left join lateral (
  select count(*) as cnt from research_notes rn where rn.pitch_id = p.id
) n on true
order by p.created_at desc;

-- ------------------------------------------------------------
-- 2) 출고 기사 — 발제가 실제 기사로 이어진 것만
-- ------------------------------------------------------------
create or replace view v_출고기사 as
select
  ac.owner_name                                   as 기자,
  ac.owner_org                                    as 소속,
  p.title                                         as 발제,
  case s.article_kind
    when 'source'  then '취재 제안서'
    when 'press'   then '보도자료 발제'
    when 'rewrite' then '리라이팅'
  end                                             as 출발점,
  a.article_url                                   as 기사링크,
  (a.submitted_at at time zone 'Asia/Seoul')      as 출고일시,
  (a.submitted_at - p.created_at)                 as 소요시간
from articles a
join sessions s      on s.id = a.session_id
join access_codes ac on ac.id = s.access_code_id
left join pitches p  on p.id = a.pitch_id
order by a.submitted_at desc;

-- ------------------------------------------------------------
-- 3) 기자별 현황 — 한 줄에 한 사람
-- ------------------------------------------------------------
create or replace view v_기자별_현황 as
select
  ac.owner_name                                                   as 기자,
  ac.owner_org                                                    as 소속,
  ac.code                                                         as 접근코드,
  ac.is_active                                                    as 사용가능,
  count(p.id)                                                     as 선택한_발제,
  count(*) filter (where s.article_kind = 'source')               as 취재제안서,
  count(*) filter (where s.article_kind = 'press')                as 보도자료발제,
  count(distinct art.id)                                          as 출고기사,
  (max(p.created_at) at time zone 'Asia/Seoul')                   as 마지막_활동
from access_codes ac
left join sessions s   on s.access_code_id = ac.id
left join pitches p    on p.session_id = s.id
left join articles art on art.session_id = s.id
group by ac.id, ac.owner_name, ac.owner_org, ac.code, ac.is_active
order by count(p.id) desc, ac.owner_name;

-- ------------------------------------------------------------
-- 4) 오늘 사용량 — 한도 대상(billable)만 카운트
--    백엔드 auth.get_daily_usage() 와 같은 기준이어야 한다.
-- ------------------------------------------------------------
create or replace view v_사용량_오늘 as
select
  ac.owner_name                                    as 기자,
  ac.code                                          as 접근코드,
  ac.daily_limit                                   as 일일한도,
  count(ul.id)                                     as 오늘_사용,
  greatest(ac.daily_limit - count(ul.id), 0)       as 남은_횟수,
  coalesce(sum(ul.input_tokens + ul.output_tokens), 0) as 오늘_토큰
from access_codes ac
left join usage_logs ul
       on ul.access_code_id = ac.id
      and ul.billable
      -- 한국 시간 자정 기준
      and ul.created_at >= date_trunc('day', now() at time zone 'Asia/Seoul')
                           at time zone 'Asia/Seoul'
group by ac.id, ac.owner_name, ac.code, ac.daily_limit
order by count(ul.id) desc;

-- ------------------------------------------------------------
-- 5) 월간 사용량 — 기능별 호출 수와 토큰 (실제 비용 파악용)
-- ------------------------------------------------------------
create or replace view v_사용량_월간 as
select
  to_char(ul.created_at at time zone 'Asia/Seoul', 'YYYY-MM')  as 월,
  ac.owner_name                                                as 기자,
  count(*)                                                     as 총_호출,
  count(*) filter (where ul.action = 'plan')                   as 발제추천,
  count(*) filter (where ul.action = 'press_pitch')            as 보도자료발제,
  count(*) filter (where ul.action = 'rewrite_target')         as 후보발굴,
  count(*) filter (where ul.action = 'rewrite')                as 리라이팅,
  count(*) filter (where ul.action = 'draft')                  as 초안,
  coalesce(sum(ul.input_tokens), 0)                            as 입력토큰,
  coalesce(sum(ul.output_tokens), 0)                           as 출력토큰
from usage_logs ul
join access_codes ac on ac.id = ul.access_code_id
group by 1, ac.id, ac.owner_name
order by 1 desc, count(*) desc;

commit;
