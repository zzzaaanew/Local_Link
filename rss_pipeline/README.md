# Local-Link RSS Automation Pipeline

이 프로젝트는 주요 언론사(사회/경제/지역)의 RSS 피드에서 최신 기사를 수집하여 지식 그래프 형태(Knowledge Graph)로 추출한 뒤 Neo4j DB에 적재하는 완전 자동화 파이프라인입니다. 

실제 서비스 환경(Production)에서 안정적으로 동작하도록 **API 요금 절감을 위한 중복 처리 방지**, **LLM 응답 오류 방어**, **체계적인 로깅 시스템**이 적용되어 있습니다.

## 🚀 주요 기능 및 파일 구성
* **Fetcher (`fetcher.py`)**: `newspaper3k`를 이용하여 RSS 피드(KBS, SBS, MBC, JTBC, YTN, 동아일보, 한겨레 등)에서 뉴스 기사 원문 텍스트를 크롤링합니다.
* **Extractor (`extractor.py`)**: Anthropic Claude 3.5 Sonnet 모델을 사용하여 기사 텍스트를 지식그래프 V2 스키마(CentralAction, Program, LocalRegion, LocalIssue 등) JSON 구조로 추출합니다. LLM이 잘못된 JSON 포맷을 반환할 경우를 대비한 예외 처리(Error Handling)가 적용되어 있습니다.
* **Loader (`loader.py`)**: 
  - **중복 방지 (Idempotency):** 추출 전, 해당 기사의 URL을 Neo4j의 `ProcessedArticle` 노드로 조회하여 이미 처리된 기사인지 판별합니다.
  - **데이터 적재:** 새 기사의 경우 추출된 JSON 구조를 Neo4j DB에 `MERGE` 문법으로 적재하여 기존 지역/이슈 노드와 관계를 형성합니다.
* **Main (`main.py`)**: 위 과정을 조율합니다. 파이썬 기본 `logging` 모듈을 통해 실행 로그를 체계적으로 기록하며, LLM API의 Rate Limit을 회피하기 위해 배치 단위(기본 5개)로 묶어서 실행하고 대기(`SLEEP_SECONDS`) 시간을 갖습니다.

## 💻 로컬 실행 방법

1. **의존성 패키지 설치**
```bash
pip install -r requirements.txt
```
*(주의: `newspaper3k`, `lxml_html_clean` 등 크롤링 필수 라이브러리가 포함되어 있습니다.)*

2. **`.env` 파일 설정**
프로젝트 루트 폴더에 `.env` 파일을 생성하고 아래 변수를 입력하세요.
```env
ANTHROPIC_API_KEY=sk-ant-api03-...
NEO4J_URI=neo4j+s://...
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
```

3. **파이프라인 실행**
```bash
python main.py
```

## ☁️ 서버(Railway 등) 배포 가이드

실제 서비스에 단독 Cron Job으로 배포하기 위한 가이드입니다. (백엔드 서버와 자원 및 패키지를 분리하여 독립적으로 돌리는 것을 권장합니다.)

1. **Environment Variables**: Railway 대시보드 (Variables 탭)에 `.env`와 동일한 환경변수 4개를 반드시 추가합니다.
2. **크론(Cron) 스케줄러 세팅**: 
   - Railway의 해당 서비스 설정에서 **Cron Jobs** 기능을 켭니다.
   - 실행 명령어(Command): `python main.py`
   - 스케줄 식(Schedule): `0 2 * * *` (매일 새벽 2시 실행) 등 원하는 주기를 입력합니다.
3. **로그 모니터링**: 실행 시 Railway의 Deployments 로그창에서 `[main - INFO - Scraping: 기사제목]` 형태의 체계적인 로그를 통해 정상 작동 여부를 확인할 수 있습니다.
