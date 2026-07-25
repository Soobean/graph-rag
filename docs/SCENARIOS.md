# 현재 지원 시나리오 총정리

> 마지막 업데이트: 2026-02-24
> 기준: main 브랜치 최신 코드 + 테스트 1004건 기반

---

## 1. 자연어 질의응답 (LangGraph Pipeline)

핵심 파이프라인 경로:
```
질문 → IntentEntityExtractor → QueryDecomposer → [CacheChecker] → ConceptExpander
     → EntityResolver → CypherGenerator → GraphExecutor → ResponseGenerator
```

### 1.1 Intent별 지원 시나리오

| # | Intent | 설명 | RETURN 스타일 | 시나리오 예시 |
|---|--------|------|--------------|--------------|
| A | `personnel_search` | 인력 검색/추천 | TYPE A (그래프) | "Python 고급 이상 개발자 찾아줘" |
| B | `project_matching` | 프로젝트 매칭 | TYPE A (그래프) | "챗봇 리뉴얼 프로젝트에 누가 참여해?" |
| C | `relationship_search` | 관계 탐색 | TYPE A (그래프) | "김철수와 같은 프로젝트에 참여한 사람은?" |
| D | `org_analysis` | 조직 분석 | TYPE B (집계) | "부서별 평균 시급은?" |
| E | `mentoring_network` | 멘토링 네트워크 | TYPE A (그래프) | "김철수의 멘티는 누구야?" |
| F | `certificate_search` | 자격증 검색 | TYPE B (집계) | "정보처리기사 보유자 목록" |
| G | `path_analysis` | 경로 분석 | TYPE A (그래프) | "김철수와 박지우는 어떻게 연결되어 있어?" |
| H | `ontology_update` | 온톨로지 수정 | (별도 핸들러) | "LangGraph를 스킬로 추가해줘" |
| I | `global_analysis` | 거시적 분석 | TYPE B (집계) | "전사 스킬 분포 Top 10은?" |

### 1.2 TYPE A (그래프 시각화) 시나리오 — 상세

> 노드/관계를 직접 반환 → 프론트엔드에서 인터랙티브 그래프로 렌더링

**인력 검색 (personnel_search)**
- 특정 스킬 보유자 검색: "React 할 수 있는 사람"
- 숙련도 필터링: "Python 고급 이상 전문가"
- 가용성 필터링: "현재 투입 가능한 Java 개발자"
- 복합 조건: "ML 고급 + Python 전문가 + 가용한 인력"

**프로젝트 매칭 (project_matching)**
- 프로젝트 참여자 조회: "챗봇 리뉴얼 프로젝트 팀원은?"
- 프로젝트-스킬 관계: "AI 추천엔진 프로젝트에 필요한 스킬은?"
- 역방향 매칭: "김철수가 참여한 프로젝트들"

**관계 탐색 (relationship_search)**
- 동료 관계: "김철수와 같은 프로젝트에 일하는 사람"
- 2-hop 관계: "김철수 동료의 스킬 목록"
- 공통 스킬: "김철수와 박지우의 공통 스킬"

**멘토링 네트워크 (mentoring_network)**
- 멘토-멘티 조회: "김철수의 멘티들"
- 멘토링 체인: "멘토의 멘티가 참여한 프로젝트"
- 3-hop 탐색: "멘티의 프로젝트 동료 스킬"

**경로 분석 (path_analysis)**
- 두 사람 간 연결 경로: "김철수와 박지우 사이의 관계"
- 프로젝트 경유 경로: 중간 프로젝트를 통한 간접 연결

### 1.3 TYPE B (집계/통계) 시나리오 — 상세

> 속성 별칭으로 반환 → 텍스트 기반 통계 응답

**조직 분석 (org_analysis)**
- 부서별 통계: "부서별 평균 시급이 가장 높은 곳은?"
- 인력 구성: "부서별 인력 수와 평균 스킬 보유 개수"
- 예산 분석: "부서별 예산 대비 프로젝트 예산 비율"

**자격증 검색 (certificate_search)**
- 자격증 보유자 집계: "자격증별 보유 인원 Top 10"
- 복합 조건: "정보처리기사 보유자 중 프로젝트 참여 현황"

**거시적 분석 (global_analysis)**
- 전사 스킬 분포: "가장 많이 보유한 스킬 Top 10"
- 프로젝트 현황: "프로젝트 타입별 평균 예산과 기간"
- 인력 추이: "연도별 신규 입사자 추이"
- 오피스 통계: "오피스별 부서 수, 인원, 예산"
- 공수 분석: "직원별 실제 투입시간 vs 배정시간 갭"
- 초과 배정: "max_projects를 초과해서 배정된 직원"
- 수요-공급 갭: "market_demand=high인데 보유 인력 부족한 스킬"

### 1.4 특수 라우팅 시나리오

**캐시 히트 (Vector Search)**
- 이전에 유사한 질문이 있으면 캐시된 Cypher를 재활용
- 경로: `CacheChecker → CypherGenerator(cached) → GraphExecutor → ResponseGenerator`

**엔티티 미해결 → 명확화 요청**
- "홍길동 스킬 알려줘" (DB에 홍길동 없음) → ClarificationHandler가 "혹시 김길동을 말씀하신 건가요?" 응답

**집계 Intent + 미해결 엔티티 → Cypher 생성 강행**
- `global_analysis`, `org_analysis`, `mentoring_network`, `certificate_search`는 엔티티 없이도 진행
- 예: "부서별 평균" → 특정 엔티티 불필요 → Cypher 바로 생성

**온톨로지 업데이트**
- "LangGraph를 스킬로 추가해줘" → `OntologyUpdateHandler`로 라우팅
- 대화 후속 확인: "네" / "응 추가해" → 이전 컨텍스트에서 추가 대상 판단

**unknown Intent → 즉시 응답**
- 분류 불가 질문 → `ResponseGenerator`로 직행하여 "잘 이해하지 못했습니다" 류 응답

### 1.5 파이프라인 보조 기능

| 기능 | 설명 |
|------|------|
| **개념 확장** | 온톨로지 시소러스로 동의어 확장 (Python → 파이썬, py) |
| **한국어 접미사 제거** | "챗봇 리뉴얼 프로젝트" → "챗봇 리뉴얼"으로 suffix strip |
| **대소문자 무시** | 모든 이름 비교에 `toLower()` 적용 |
| **Multi-hop 분해** | 복잡한 질문을 여러 하위 쿼리로 분해 후 체인 |
| **NOT IN 구문 자동 수정** | SQL 스타일 `x NOT IN [...]` → Cypher `NOT x IN [...]` |
| **Adaptive Ontology** | 미해결 엔티티를 백그라운드 학습 → 온톨로지 제안 자동 생성 |

---

## 2. 스트리밍 응답

| 엔드포인트 | 방식 | 이벤트 타입 |
|-----------|------|------------|
| `POST /api/v1/query/stream` | SSE (Server-Sent Events) | `step`, `metadata`, `chunk`, `done`, `error` |

**실시간 파이프라인 단계 표시:**
- 각 노드 완료 시 `step` 이벤트 즉시 전송
- 프론트엔드에서 "의도 분석 중..." → "Cypher 생성 중..." → "결과 조회 중..." 순차 표시
- 캐시 히트 시 6단계, 미스 시 8단계 동적

---

## 3. 프로젝트 스태핑 (직접 Cypher, Pipeline 우회)

> `ProjectStaffingService` — LangGraph를 거치지 않고 직접 Neo4j 쿼리

| # | 시나리오 | 엔드포인트 |
|---|---------|-----------|
| 1 | **후보자 검색** | `POST /api/v1/staffing/candidates` |
| 2 | **스태핑 계획 생성** | `POST /api/v1/staffing/plan` |
| 3 | **예산 분석** | `POST /api/v1/staffing/budget` |
| 4 | **프로젝트 목록** | `GET /api/v1/staffing/projects` |

**후보자 검색 필터:**
- 프로젝트 REQUIRES 스킬 매칭
- 숙련도 필터 (초급/중급/고급/전문가)
- 비용 필터 (effective_rate ≤ max_hourly_rate)
- 가용성 필터 (available/partial만)
- max_projects 제약 확인

**스태핑 계획:**
- 스킬별 Top N 후보 자동 선정
- 인당 예상 투입 시간 계산
- 총 스태핑 비용 산출
- 팀원별 비용 내역

---

## 4. 그래프 편집 (CRUD)

| 대상 | 작업 | 엔드포인트 |
|------|------|-----------|
| 노드 | 생성 | `POST /api/v1/graph/nodes` |
| 노드 | 검색 (라벨/이름 필터) | `GET /api/v1/graph/nodes` |
| 노드 | 상세 조회 | `GET /api/v1/graph/nodes/{id}` |
| 노드 | 수정 (속성 갱신/삭제) | `PATCH /api/v1/graph/nodes/{id}` |
| 노드 | 삭제 (force=DETACH DELETE) | `DELETE /api/v1/graph/nodes/{id}` |
| 엣지 | 생성 | `POST /api/v1/graph/edges` |
| 엣지 | 조회 | `GET /api/v1/graph/edges/{id}` |
| 엣지 | 삭제 | `DELETE /api/v1/graph/edges/{id}` |
| 분석 | 삭제 영향도 미리보기 | `GET /api/v1/graph/nodes/{id}/impact` |
| 분석 | 이름 변경 영향도 | `POST /api/v1/graph/nodes/{id}/impact/rename` |

**화이트리스트 기반 검증:**
- 허용된 라벨만 생성/수정 가능 (Employee, Skill, Project, Department 등)
- 허용된 관계 타입만 생성 가능 (HAS_SKILL, WORKS_ON, BELONGS_TO 등)

---

## 5. 시각화

| 시나리오 | 엔드포인트 | 설명 |
|---------|-----------|------|
| 서브그래프 탐색 | `POST /visualization/subgraph` | 특정 노드 중심 N-depth 그래프 |
| 커뮤니티 구조 | `POST /visualization/community-graph` | GDS 커뮤니티 시각화 |
| 쿼리 결과 그래프 | `POST /visualization/query-result` | Cypher 결과 → 인터랙티브 그래프 변환 |
| 쿼리 경로 시각화 | `POST /visualization/query-path` | 경로 탐색 결과 시각화 |
| 스키마 탐색 | `GET /visualization/schema` | DB 라벨/관계 구조 시각화 |

**프론트엔드 그래프 렌더링:**
- React Flow (@xyflow/react) 기반 인터랙티브 그래프
- d3-force 물리 시뮬레이션 레이아웃
- 라벨별 색상 분류 (Employee=emerald, Skill=blue, Project=violet 등)
- 다중 center 노드 원형 배치 + 충돌 회피
- MiniMap 지원

---

## 6. 분석 (GDS — Graph Data Science)

| # | 시나리오 | 엔드포인트 |
|---|---------|-----------|
| 1 | 그래프 프로젝션 생성 | `POST /analytics/projection/create` |
| 2 | 커뮤니티 탐지 (Louvain) | `POST /analytics/community/detect` |
| 3 | 유사 직원 찾기 | `POST /analytics/similarity/similar-employees` |
| 4 | 팀 추천 | `POST /analytics/team/recommend` |

**커뮤니티 탐지**: 공유 스킬 기반으로 직원 그룹 자동 클러스터링
**유사 직원**: 공유 스킬 수 기반 유사도 점수 산출
**팀 추천**: 필요 스킬셋 → 최적 팀 구성 추천 (팀 크기 지정 가능)

---

## 7. 데이터 수집 (Ingestion)

| 시나리오 | 엔드포인트 |
|---------|-----------|
| 파일 업로드 (CSV/Excel) | `POST /ingest/upload` |
| 작업 상태 확인 | `GET /ingest/status/{job_id}` |
| 전체 수집 통계 | `GET /ingest/stats` |

- 최대 100MB 파일
- 비동기 백그라운드 처리
- 자동 엔티티 추출 + 그래프 로딩
- 경로 순회 공격 방지 (sanitization)

---

## 8. 온톨로지 관리

### 8.1 읽기 전용 (일반 사용자)
| 시나리오 | 엔드포인트 |
|---------|-----------|
| 온톨로지 스키마 조회 | `GET /ontology/schema` |
| 개념 스타일 조회 | `GET /ontology/concept/{category}/{name}/style` |

### 8.2 관리자 (Admin)
| 시나리오 | 엔드포인트 |
|---------|-----------|
| 제안 목록/검색 | `GET /ontology/admin/proposals` |
| 제안 상세 | `GET /ontology/admin/proposals/{id}` |
| 제안 생성 | `POST /ontology/admin/proposals` |
| 제안 수정 | `PATCH /ontology/admin/proposals/{id}` |
| 개별 승인 | `POST /ontology/admin/proposals/{id}/approve` |
| 개별 거절 (사유 포함) | `POST /ontology/admin/proposals/{id}/reject` |
| 일괄 승인 | `POST /ontology/admin/proposals/batch-approve` |
| 일괄 거절 | `POST /ontology/admin/proposals/batch-reject` |
| 통계 | `GET /ontology/admin/stats` |

**Adaptive Ontology 흐름:**
```
미해결 엔티티 발생 → OntologyLearner가 백그라운드 학습
→ 제안(Proposal) 자동 생성 → Admin UI에서 승인/거절
→ 승인 시 온톨로지 반영 (동의어, 계층 구조)
```

---

## 9. 인증/권한 (RBAC)

| 역할 | 권한 |
|------|------|
| `admin` | 전체 접근 (그래프 편집, 온톨로지 관리, 분석) |
| `manager` | 조회 + 스태핑 + 일부 분석 |
| `editor` | 조회 + 그래프 편집 |
| `viewer` | 조회 전용 |

- JWT 기반 인증 (기본 OFF — 데모 모드)
- `AUTH_ENABLED=true`로 활성화
- Compare 페이지에서 4개 역할로 동일 질문 비교 가능

---

## 10. 프론트엔드 UI 페이지

| 페이지 | 경로 | 핵심 기능 |
|--------|------|----------|
| **채팅** | `/` | 자연어 Q&A + 실시간 그래프 시각화 |
| **비교** | `/compare` | 4개 역할로 동일 질문 결과 비교 |
| **스태핑** | `/staffing` | 프로젝트별 후보자 검색 + 비용 계획 |
| **관리 - 개요** | `/admin/overview` | 시스템 상태 + 그래프 통계 대시보드 |
| **관리 - 온톨로지** | `/admin/ontology` | 제안 승인/거절 + 통계 |
| **관리 - 수집** | `/admin/ingest` | CSV/Excel 업로드 + 작업 추적 |
| **관리 - 분석** | `/admin/analytics` | 커뮤니티/유사도/팀추천 |
| **관리 - 그래프 편집** | `/admin/graph-edit` | 노드/엣지 CRUD + 영향도 분석 |

---

## 11. 검증된 HR 질문 시나리오 (20개 골든셋)

실제 테스트에 사용된 20개 질문:

| # | 질문 | 카테고리 |
|---|------|---------|
| 1 | 부서별 평균 시급이 가장 높은 부서는? | 조직 분석 |
| 2 | 직원들의 career_level 분포 vs position_target 가이드라인 | 조직 분석 |
| 3 | 연도별 신규 입사자 추이 | 글로벌 분석 |
| 4 | max_projects를 초과해서 배정된 직원 | 글로벌 분석 |
| 5 | 가장 많이 보유한 스킬 Top 10 | 글로벌 분석 |
| 6 | market_demand=high인데 보유 인력 부족한 스킬 | 글로벌 분석 |
| 7 | Python/ML 전문가급 분포 | 인력 검색 |
| 8 | 직무별 평균 스킬 보유 개수 & effectiveness_rate | 조직 분석 |
| 9 | 프로젝트 required_skills 충족도 by 부서 | 프로젝트 매칭 |
| 10 | 프로젝트 상태별 예산 집행률 | 글로벌 분석 |
| 11 | 인원 배정 부족 프로젝트 | 글로벌 분석 |
| 12 | 참여 인원 Top 5 프로젝트 + 기여도% | 프로젝트 매칭 |
| 13 | 프로젝트 타입별 평균 예산 & 기간 | 글로벌 분석 |
| 14 | 프로젝트 예산 vs 부서 예산 비율 | 조직 분석 |
| 15 | 오피스별 부서 수, 인원, 예산 | 글로벌 분석 |
| 16 | 진행중 프로젝트의 PM 역할 분포 | 프로젝트 매칭 |
| 17 | 자격증 Top 10 보유자 + 프로젝트 참여 현황 | 자격증 검색 |
| 18 | 멘토당 평균 멘티 수 + 멘토 집중도 | 멘토링 |
| 19 | agreed_rate vs hourly_rate 차이가 큰 직원 | 글로벌 분석 |
| 20 | 직원별 실제 투입시간 vs 배정시간 갭 | 글로벌 분석 |

**현재 성적**: 10 OK / 6 COMMUNITY (global_analysis 라우팅 이슈) / 4 WRONG_ANS
→ `fix-global-analysis-routing.md` 계획으로 COMMUNITY 6건 해결 예정

---

## 12. 아직 미지원 / 제한사항

| 항목 | 상태 | 비고 |
|------|------|------|
| CommunitySummarizer 직접 라우팅 | 제거 예정 | 3개 하드코딩 쿼리만 지원 → Cypher 파이프라인으로 대체 |
| CALL {} 서브쿼리 | 미지원 | Neo4j Community Edition 제한 |
| 실시간 그래프 업데이트 알림 | 미구현 | WebSocket 미적용 |
| 다국어 (영어 외) | 부분 지원 | 한국어 중심, 영어 엔티티명은 지원 |
| 파일 업로드 후 자동 온톨로지 갱신 | 미연결 | 수집 → 온톨로지 자동 반영 파이프라인 없음 |
| 대화 히스토리 영속화 | 메모리만 | MemorySaver 기본, SqliteSaver 주입 가능하나 미설정 |
