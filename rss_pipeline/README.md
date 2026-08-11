# Local-Link RSS Automation Pipeline

이 프로젝트는 주요 언론사(사회/경제) RSS 피드에서 기사를 수집하여 지식 그래프 형태(Knowledge Graph)로 추출한 뒤 Neo4j DB에 적재하는 자동화 파이프라인입니다.

## 기능
* **Fetcher (`fetcher.py`)**: `newspaper3k`를 이용하여 RSS 피드(KBS, SBS, MBC, JTBC, YTN, 동아일보, 한겨레 등)에서 뉴스 기사 원문 텍스트를 크롤링합니다.
* **Extractor (`extractor.py`)**: Anthropic Claude 3.5 Sonnet 모델을 사용하여 기사 텍스트를 V2 스키마(CentralAction, Program, LocalRegion, LocalIssue 등) JSON 구조로 추출합니다.
* **Loader (`loader.py`)**: 추출된 JSON 구조를 Neo4j DB에 `MERGE` 문법으로 적재하여, 중복 노드 생성을 방지하고 기존 노드와 엣지(관계성)를 연결합니다.
* **Main (`main.py`)**: 위 과정을 조율하며, LLM API의 Rate Limit을 회피하기 위해 배치 단위(기본 5개)로 묶어서 실행하고 대기(`SLEEP_SECONDS`) 시간을 갖습니다.

## 로컬 실행 방법

1. 의존성 패키지 설치
```bash
pip install -r requirements.txt
```

2. `.env` 파일 설정
프로젝트 루트 폴더에 `.env` 파일을 생성하고 아래 변수를 입력하세요.
```env
ANTHROPIC_API_KEY=sk-ant-api03-...
NEO4J_URI=neo4j+s://...
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
```

3. 실행
```bash
python main.py
```

## 서버(Railway 등) 배포 가이드

실제 서비스에 올리기 위해 Railway 플랫폼을 기준으로 작성되었습니다. 저장소 최상단에 있는 `Dockerfile`과 `railway.toml`이 배포 시 사용됩니다.

1. **GitHub 연동**: 이 `rss_pipeline` 폴더가 포함된 깃허브 레포지토리를 Railway에 연동합니다.
2. **Environment Variables**: Railway 대시보드 (Variables 탭)에 `.env`와 동일한 환경변수들을 추가합니다.
   * `ANTHROPIC_API_KEY`
   * `NEO4J_URI`
   * `NEO4J_USERNAME`
   * `NEO4J_PASSWORD`
3. **크론(Cron) 스케줄러 세팅**: 
   매일 밤마다(예: 매일 자정) 코드가 한 번씩 돌게 하려면 `railway.toml`에 cron 설정을 추가하거나 백엔드(예: Node.js/Python FastAPI 서버 등)에서 `python main.py`를 서브프로세스로 주기적으로 호출하게 설정하면 됩니다.
   * 단순히 일회성 스크립트로 동작하길 원할 경우, Railway의 "Cron Jobs" 기능을 활성화하고 스케줄 식(예: `0 2 * * *` - 매일 새벽 2시)을 입력하세요.
