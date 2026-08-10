# 📊 Local-Link 지식 그래프 (Neo4j)

LLM + Neo4j를 결합한 경북 지역 언론 지원 파이프라인의 **그래프 DB 레이어**입니다.
Neo4j Aura (클라우드) 기준으로 작성되어 있습니다.

## 파일 구조

| 파일 | 역할 |
|---|---|
| `setup_neo4j.py` | **최초 1회 실행** — DB에 `BaseNode(name)` 유니크 제약 조건 생성 |
| `ingest_graph.py` | 노드·엣지를 Neo4j에 적재하는 함수 (`ingest_ontology`) |
| `graph.py` | 파이프라인 Phase 2 — 키워드로 그래프를 조회해 팩트 문장 반환 |
| `requirements.txt` | 필요한 Python 패키지 목록 |

스키마 설계는 루트의 [`Node&Edge_v2.md`](../Node&Edge_v2.md)를 참고하세요.

---

## 🚀 맥북에서 처음 세팅하는 법

### 1. 환경변수 설정
프로젝트 루트(또는 `knowledge_graph/`)에 `.env` 파일을 생성하세요.
```env
AURA_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
AURA_USER=neo4j
AURA_PASSWORD=your_password_here
```
> ⚠️ `.env` 파일은 `.gitignore`에 포함되어 있어 GitHub에 올라가지 않습니다.
> 실제 값은 [Neo4j Aura 콘솔](https://console.neo4j.io) 또는 팀에서 별도 공유된 자격증명을 사용하세요.

### 2. 패키지 설치
```bash
pip install -r requirements.txt
```

### 3. DB 초기 제약 조건 세팅 (최초 1회)
```bash
python setup_neo4j.py
```

### 4. 데이터 적재
`ingest_graph.py`의 `ingest_ontology(nodes_data, relationships)` 함수를 호출합니다.
파일 하단의 `if __name__ == "__main__":` 블록에 샘플 예시가 포함되어 있습니다.
```bash
python ingest_graph.py
```

---

## 🗺️ 그래프 온톨로지 구조 요약

**노드 타입 (모두 `BaseNode` 라벨 공유, `name`이 PK)**
- `CentralAction` — 중앙정부 정책·제도
- `Program` — 지역 정책·사업 (파이프라인의 핵심 허브)
- `LocalRegion` — 행정구역 (경북, 포항시 등)
- `LocalAsset` — 지역 인프라·기관·산업단지
- `Stakeholder` — 기관, 기업, 주민 등 이해관계자
- `LocalIssue` — 지역 현안
- `EcoIndicator` — 통계 데이터
- `DataPoint` — 기사화 시 확인할 추가 자료
- `ReportingFrame` — 기사 작성 관점

**주요 관계 (Edge)**
```
(Program)-[:LOCATED_IN]->(LocalRegion)
(Program)-[:INVOLVES]->(Stakeholder)
(Program)-[:HAS_INTERVIEW_TARGET]->(Stakeholder)
(Program)-[:REQUIRES_CHECK]->(DataPoint)
(Program)-[:SUGGESTS_FRAME]->(ReportingFrame)
(LocalIssue)-[:CONTRIBUTES_TO]->(LocalIssue)
(NationalIssue)-[:LOCALIZED_TO]->(LocalIssue)
```
전체 엣지 정의는 [`Node&Edge_v2.md`](../Node&Edge_v2.md) 참고.
