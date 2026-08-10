-- ============================================================
-- 관리자 조회용 뷰 (전체) — 적용(up)
-- 선행: 005, 006, 007
-- 되돌리기: 008_views_down.sql
--
-- 006 의 뷰를 모두 포함하고, 추천물·입력자료 뷰를 더했습니다.
-- 006 을 이미 실행했더라도 이 파일만 다시 돌리면 전부 최신 정의로 덮어씁니다.
--
-- Supabase 대시보드 → Table Editor 왼쪽 목록에서 바로 열립니다.
-- 조인 없이 읽히도록 컬럼명을 한글로 두었습니다.
--
--   ── 작업 ───────────────────────────────────
--   v_작업목록       누가 어떤 발제를 선택했고 어디까지 갔나  ★ 주력
--   v_출고기사       누가 어떤 기사를 썼나
--   ── 자료 ───────────────────────────────────
--   v_입력자료       기자가 넣은 보도자료·기사 원문
--   v_취재물         기자가 입력한 취재 내용
--   v_추천내역       AI가 무엇을 추천했고 무엇을 골랐나
--   v_제안서보관     생성된 취재 제안서 전문
--   ── 사람·비용 ──────────────────────────────
--   v_기자별_현황    한 줄에 한 사람
--   v_사용량_오늘    오늘 사용/남은 횟수
--   v_사용량_월간    월별 호출·토큰
-- ============================================================
begin;

-- 먼저 지우고 다시 만든다.
-- create or replace view 는 컬럼 이름·순서·타입이 바뀌면
-- "cannot change name of view column" 으로 실패한다. 뷰 정의를 손볼 때마다
-- 걸리지 않도록 매번 새로 만든다.
drop view if exists v_작업목록      cascade;
drop view if exists v_출고기사      cascade;
drop view if exists v_입력자료      cascade;
drop view if exists v_취재물        cascade;
drop view if exists v_추천내역      cascade;
drop view if exists v_제안서보관    cascade;
drop view if exists v_기자별_현황   cascade;
drop view if exists v_사용량_오늘   cascade;
drop view if exists v_사용량_월간   cascade;

-- ============================================================
-- 작업
-- ============================================================

-- 누가 어떤 발제를 선택했고 어디까지 갔는가 (한 줄 = 작업 1건)
create view v_작업목록 as
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
left join lateral (
  select d.id from drafts d where d.pitch_id = p.id
  order by d.created_at desc limit 1
) d on true
left join lateral (
  select a.id, a.article_url from articles a where a.pitch_id = p.id
  order by a.submitted_at desc limit 1
) a on true
left join lateral (
  select count(*) as cnt from research_notes rn where rn.pitch_id = p.id
) n on true
-- archived = 구버전에서 넘어온, 기자가 고르지 않은 발제. 목록에 섞이면 방해된다.
where p.status <> 'archived'
order by p.created_at desc;

-- 발제가 실제 기사로 이어진 것만
create view v_출고기사 as
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

-- ============================================================
-- 자료 — 기자가 넣은 것과 AI가 만든 것
-- ============================================================

-- 기자가 입력한 보도자료·기사 원문
create view v_입력자료 as
select
  ac.owner_name                                    as 기자,
  ac.owner_org                                     as 소속,
  case s.article_kind
    when 'press'   then '보도자료'
    when 'rewrite' then '리라이팅 원문'
    when 'source'  then '(원문 없음)'
  end                                              as 종류,
  s.source_title                                   as 제목,
  length(s.source_text)                            as 글자수,
  left(s.source_text, 300)                         as 앞부분,
  s.user_prompt                                    as 추가요청,
  s.source_text                                    as 전문,
  (s.created_at at time zone 'Asia/Seoul')         as 입력일시,
  s.id                                             as session_id
from sessions s
join access_codes ac on ac.id = s.access_code_id
where s.source_text is not null
order by s.created_at desc;

-- 기자가 입력한 취재 내용
create view v_취재물 as
select
  ac.owner_name                                    as 기자,
  ac.owner_org                                     as 소속,
  p.title                                          as 발제,
  length(rn.content)                               as 글자수,
  rn.content                                       as 취재내용,
  (rn.created_at at time zone 'Asia/Seoul')        as 입력일시
from research_notes rn
join pitches p       on p.id = rn.pitch_id
join sessions s      on s.id = p.session_id
join access_codes ac on ac.id = s.access_code_id
order by rn.created_at desc;

-- AI가 무엇을 추천했고 기자가 무엇을 골랐나
create view v_추천내역 as
select
  ac.owner_name                                    as 기자,
  ac.owner_org                                     as 소속,
  case sg.kind
    when 'plan'           then '취재 제안서'
    when 'press_pitch'    then '보도자료 발제'
    when 'rewrite_target' then '리라이팅 후보'
  end                                              as 종류,
  case when sg.picked then '선택함' else '' end     as 선택,
  sg.position                                      as 순번,
  sg.title                                         as 제목,
  sg.why                                           as 추천이유,
  sg.org                                           as 기관,
  sg.timing                                        as 시점,
  sg.url                                           as 원문링크,
  (sg.created_at at time zone 'Asia/Seoul')        as 추천일시,
  sg.batch_id                                      as 묶음
from suggestions sg
join access_codes ac on ac.id = sg.access_code_id
order by sg.created_at desc, sg.position;

-- 생성된 취재 제안서 전문 (저장하지 않은 것도 남는다)
create view v_제안서보관 as
select
  ac.owner_name                                    as 기자,
  sg.title                                         as 제목,
  sg.org                                           as 기관,
  sg.region                                        as 지역,
  sg.timing                                        as 시점,
  sg.scheduled_at                                  as 발표예정,
  case when sg.picked then '저장함' else '안 함' end as 저장여부,
  sg.why                                           as 발제이유,
  sg.body                                          as 제안서전문,
  (sg.created_at at time zone 'Asia/Seoul')        as 생성일시
from suggestions sg
join access_codes ac on ac.id = sg.access_code_id
where sg.kind = 'plan'
order by sg.created_at desc, sg.position;

-- ============================================================
-- 사람 · 비용
-- ============================================================

-- 한 줄에 한 사람
create view v_기자별_현황 as
select
  ac.owner_name                                                as 기자,
  ac.owner_org                                                 as 소속,
  ac.code                                                      as 접근코드,
  ac.is_active                                                 as 사용가능,
  coalesce(w.선택한_발제, 0)                                    as 선택한_발제,
  coalesce(w.취재제안서, 0)                                     as 취재제안서,
  coalesce(w.보도자료발제, 0)                                   as 보도자료발제,
  coalesce(w.출고기사, 0)                                       as 출고기사,
  coalesce(g.추천받음, 0)                                       as 추천받음,
  case when coalesce(g.추천받음, 0) = 0 then null
       else round(coalesce(g.선택함, 0)::numeric
                  / g.추천받음 * 100, 1) end                     as 선택률_pct,
  coalesce(i.입력자료, 0)                                       as 입력자료,
  (w.마지막_활동 at time zone 'Asia/Seoul')                      as 마지막_활동
from access_codes ac
left join lateral (
  select
    count(p.id)                                       as 선택한_발제,
    count(p.id) filter (where s.article_kind = 'source') as 취재제안서,
    count(p.id) filter (where s.article_kind = 'press')  as 보도자료발제,
    count(distinct art.id)                            as 출고기사,
    max(p.created_at)                                 as 마지막_활동
  from sessions s
  left join pitches p    on p.session_id = s.id and p.status <> 'archived'
  left join articles art on art.session_id = s.id
  where s.access_code_id = ac.id
) w on true
left join lateral (
  select count(*) as 추천받음, count(*) filter (where picked) as 선택함
  from suggestions where access_code_id = ac.id
) g on true
left join lateral (
  select count(*) as 입력자료
  from sessions where access_code_id = ac.id and source_text is not null
) i on true
order by coalesce(w.선택한_발제, 0) desc, ac.owner_name;

-- 오늘 사용량 (한도 대상만) — 백엔드 usage.get_daily() 와 같은 기준
create view v_사용량_오늘 as
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
      and ul.created_at >= date_trunc('day', now() at time zone 'Asia/Seoul')
                           at time zone 'Asia/Seoul'
group by ac.id, ac.owner_name, ac.code, ac.daily_limit
order by count(ul.id) desc;

-- 월별·기자별 호출과 토큰 (실제 비용 파악용)
create view v_사용량_월간 as
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
