# Node

모든 노드는 1회용 `_id` 필드가 삭제되었으며, 고유 식별자(Primary Key)로 **`name`** 필드를 통일하여 사용합니다. (모든 노드는 `BaseNode` 라벨을 공유하며 `name` 속성에 Unique 제약조건이 걸려 있습니다.)

• **CentralAction** (중앙정부 정책·제도·규제·예산)
  - ~~`action_id`~~ (삭제)
  - `name` (기존 `title`에서 변경, 고유 식별자)
  - `date`
  - `category`

• **Program** (지역 정책·사업·행사)
  - ~~`program_id`~~ (삭제)
  - `name` (고유 식별자)
  - `program_type`
  - `status`

• **LocalRegion** (행정구역)
  - ~~`region_id`~~ (삭제)
  - `name` (고유 식별자)
  - `level`

• **LocalAsset** (지역 고유 인프라, 랜드마크, 공공기관, 산업단지, 상권)
  - ~~`asset_id`~~ (삭제)
  - `name` (고유 식별자)
  - `asset_type`

• **Stakeholder** (기관, 기업, 주민, 수혜자, 전문가 등 이해관계자)
  - ~~`stakeholder_id`~~ (삭제)
  - `name` (고유 식별자)
  - `stakeholder_type`

• **LocalIssue** (지역 사회가 겪는 현안)
  - ~~`issue_id`~~ (삭제)
  - `name` (기존 `keyword`에서 변경, 고유 식별자)
  - `status`

• **EcoIndicator** (통계 데이터)
  - ~~`indicator_id`~~ (삭제)
  - `name` (고유 식별자)
  - `current_value`

• **DataPoint** (기사화를 위해 추가 확인해야 하는 자료)
  - ~~`data_id`~~ (삭제)
  - `name` (고유 식별자)
  - `data_type`

• **ReportingFrame** (기사 작성 관점)
  - ~~`frame_id`~~ (삭제)
  - `name` (고유 식별자)
  - `priority`

• **NationalIssue** (전국 이슈)
  - `name` (고유 식별자)

---

# A. 정책 및 사업 관계 (Policy & Program)

| Source Node | Edge | Target Node | 관계 설명 | 예시 데이터 (name 기반) |
| :--- | :--- | :--- | :--- | :--- |
| CentralAction | OPERATES | Program | 중앙정부 또는 지자체가 정책·사업을 추진 | (국토부_청년주거지원)-[:OPERATES]->(청년주거지원사업) |
| Program | LOCATED_IN | LocalRegion | 사업이 시행되는 지역 | (청년주거지원사업)-[:LOCATED_IN]->(포항시) |
| Program | TARGETS | Stakeholder | 사업의 직접적인 대상 | (청년주거지원사업)-[:TARGETS]->(포항_청년) |
| Program | INVOLVES | Stakeholder | 사업 수행에 참여하는 기관 또는 기업 | (청년주거지원사업)-[:INVOLVES]->(포항시청) |

---

# B. 지역 자산 및 현안 관계 (Local Context)

| Source Node | Edge | Target Node | 관계 설명 | 예시 데이터 (name 기반) |
| :--- | :--- | :--- | :--- | :--- |
| LocalAsset | LOCATED_IN | LocalRegion | 자산의 위치 | (유강정수장)-[:LOCATED_IN]->(포항시_남구) |
| Stakeholder | OPERATES | LocalAsset | 기관 또는 기업이 자산을 운영 | (포항시_맑은물사업본부)-[:OPERATES]->(유강정수장) |
| LocalAsset | HAS_ISSUE | LocalIssue | 자산과 연결된 지역 현안 | (포항철강산단)-[:HAS_ISSUE]->(노후화) |
| Stakeholder | AFFECTED_BY | LocalIssue | 이해관계자가 현안의 영향을 받음 | (죽도시장_상인)-[:AFFECTED_BY]->(상권침체) |

---

# C. 데이터 및 현황 관계 (Evidence)

| Source Node | Edge | Target Node | 관계 설명 | 예시 데이터 (name 기반) |
| :--- | :--- | :--- | :--- | :--- |
| EcoIndicator | MEASURES | LocalRegion | 통계가 지역의 상태를 측정 | (청년순이동)-[:MEASURES]->(포항시) |
| EcoIndicator | MEASURES | LocalAsset | 통계가 시설 또는 산업의 상태를 측정 | (산단가동률)-[:MEASURES]->(포항철강산단) |
| EcoIndicator | INDICATES | LocalIssue | 통계가 특정 현상을 보여줌 | (청년고용률)-[:INDICATES]->(청년유출) |

---

# D. 이슈 관계 (Issue Relationships)

| Source Node | Edge | Target Node | 관계 설명 | 예시 데이터 (name 기반) |
| :--- | :--- | :--- | :--- | :--- |
| LocalIssue | CONTRIBUTES_TO | LocalIssue | 하나의 현안이 다른 현안에 영향을 줌 | (청년유출)-[:CONTRIBUTES_TO]->(상권침체) |
| LocalIssue | WORSENS | LocalIssue | 하나의 현안이 다른 현안을 악화 | (대기오염)-[:WORSENS]->(주민건강악화) |

---

# E. 이해관계자 관계 (Stakeholder Relationships)

| Source Node | Edge | Target Node | 관계 설명 | 예시 데이터 (name 기반) |
| :--- | :--- | :--- | :--- | :--- |
| Stakeholder | PARTNERS_WITH | Stakeholder | 기관 간 협력 | (포항시청)-[:PARTNERS_WITH]->(포스텍) |
| Stakeholder | CONFLICTS_WITH | Stakeholder | 기관 또는 단체 간 갈등 | (지역노조)-[:CONFLICTS_WITH]->(입주기업) |
| Stakeholder | RESPONDS_TO | LocalIssue | 특정 현안에 대응 | (포항시청)-[:RESPONDS_TO]->(청년유출) |

---

# F. Journalism Ontology (기사 발제 추론)

| Source Node | Edge | Target Node | 관계 설명 | 예시 데이터 (name 기반) |
| :--- | :--- | :--- | :--- | :--- |
| Program | HAS_PREVIOUS_PROGRAM | Program | 과거 동일·유사 사업 | (2026_청년주거지원)-[:HAS_PREVIOUS_PROGRAM]->(2025_청년주거지원) |
| Program | HAS_INTERVIEW_TARGET | Stakeholder | 기사화를 위해 추천하는 취재 대상 | (청년주거지원)-[:HAS_INTERVIEW_TARGET]->(청년_수혜자) |
| Program | REQUIRES_CHECK | DataPoint | 기사화를 위해 추가 확인할 정보 | (청년주거지원)-[:REQUIRES_CHECK]->(전년도_사업효과) |
| Program | SUGGESTS_FRAME | ReportingFrame | 추천 기사 구성 방식 | (청년주거지원)-[:SUGGESTS_FRAME]->(수혜자사례) |
| NationalIssue | LOCALIZED_TO | LocalIssue | 전국 이슈를 지역 현안으로 연결 | (전기차보조금개편)-[:LOCALIZED_TO]->(캐즘_현상) |
