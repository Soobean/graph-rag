# Graph RAG 기능 카탈로그

> 이 문서는 시스템의 **사용자 관점 전체 기능 지도**입니다.
> 기술 아키텍처는 [docs/architecture/](architecture/), 검증 시나리오는 [SCENARIOS.md](SCENARIOS.md) 참고.
> 마지막 갱신: 2026-07-21 (코드 기준 전수 조사)

**한 줄 요약**: 임직원·프로젝트·스킬·조직 데이터를 지식그래프(Neo4j)로 연결하고, 자연어 질문을 LLM이 Cypher로 번역해 **관계 기반 답변 + 그래프 시각화**로 제공하는 Graph RAG 시스템.

---

## 1. 화면별 기능

### 1.1 💬 Chat (`/`) — 자연어 그래프 검색

| 기능 | 설명 |
|------|------|
| 스트리밍 Q&A | SSE 기반 실시간 응답 (`POST /api/v1/query/stream`). 토큰 단위 표시 |
| 파이프라인 단계 표시 | 각 노드 완료 즉시 단계 표시 — "의도: personnel_search (98%)", "쿼리 실행: 200건 조회" 등. 완료 후 접기/펼치기 |
| 그래프 시각화 패널 | React Flow 인터랙티브 그래프. 라벨별 색상, 미니맵, 노드 확장(+N 뱃지), 노드 상세 패널, d3-force 레이아웃 |
| 테이블 뷰 | 집계형 결과(스칼라)는 그래프 대신 표로 자동 전환 |
| 메타데이터 배지 | intent·결과 건수 표시, 실행된 Cypher 확인 가능 |
| 세션/히스토리 | 세션별 대화 유지, 전체 히스토리 삭제 |
| 온톨로지 채팅 명령 | "LangGraph를 스킬로 추가해줘" → 채팅으로 온톨로지 수정 (확인 응답 "네" 지원) |
| 데모 역할 전환 | 헤더에서 admin/manager/editor/viewer 선택 → RBAC 필터 체험 |
| 랜딩 화면 | 온톨로지 애니메이션 + 히어로, 입력창 전환 애니메이션 (framer-motion) |

### 1.2 ⚖️ Compare (`/compare`) — 접근제어 비교

| 기능 | 설명 |
|------|------|
| 4역할 동시 질의 | 동일 질문을 admin/manager/editor/viewer로 **동시 스트리밍** 실행 |
| 필터 분석 배지 | 역할별 결과 건수 + 민감 필드(단가·예산·멘토링) 접근 가능 여부 ✓/✗ — 차이 나는 항목만 표시 |
| 데이터 비교 테이블 | 4역할 메타데이터 나란히 비교 (페이지네이션) |
| 응답 그리드 | 역할별 텍스트 응답 4열 비교 |

### 1.3 👥 Staffing (`/staffing`) — 비용 기반 인력 배치

| 탭 | 기능 |
|----|------|
| ① 후보자 탐색 | 프로젝트 필요 스킬(REQUIRES)별 적격 후보 — 가용성/숙련도 갭/단가/비용 효율%/참여 부하. 행 확장 시 매칭 점수(100점) + 추천 사유 |
| ② 스태핑 플랜 | 스킬당 추천 인원 수 선택 → 총 예상 인건비 / 프로젝트 예산 / 예산 활용률 |
| ③ 예산 분석 | 계획 vs 실제 인건비, 예산 소진율, 팀원별 비용 내역 (단가·배정/실제 시간·차이%) |

**매칭 스코어 공식**: 숙련도(40, 연차 보정) + 비용 효율(35) + 가용성(25)

### 1.4 🛠️ Admin (`/admin/*`) — 관리 콘솔

| 서브페이지 | 기능 |
|-----------|------|
| Overview | 시스템 상태 + 그래프 통계 대시보드 |
| Ontology | 온톨로지 변경 제안 검토 — 필터/정렬, 개별·**일괄** 승인/거절(사유 필수), 통계(카테고리 분포, 미해결 용어 Top 10), 낙관적 락 |
| Ingest | CSV/Excel 업로드(100MB, 시트 지정, 배치 크기) → LLM 그래프 추출 → 비동기 적재, 작업 상태 추적 |
| Analytics | GDS 프로젝션 관리 + 커뮤니티 탐지(Leiden/Louvain) + 유사 직원 탐색 + 팀 추천 |
| Graph Edit | 노드/엣지 CRUD (라벨·이름 검색), **삭제 영향도 미리보기**, 이름변경 영향도 dry-run |

---

## 2. 지원 질의 유형 (파이프라인 Intent)

| Intent | 처리 질문 | 예시 |
|--------|-----------|------|
| `personnel_search` | 스킬/숙련도/가용성 기반 인력 검색 | "Python 고급 이상 개발자 찾아줘" |
| `project_matching` | 프로젝트 참여자·필요 스킬·역방향 매칭 | "챗봇 리뉴얼 프로젝트에 누가 참여해?" |
| `relationship_search` | 동료·2-hop·공통 스킬 관계 | "김철수와 같은 프로젝트에 참여한 사람은?" |
| `org_analysis` | 부서별 통계·인력 구성·예산 (집계) | "부서별 평균 시급은?" |
| `mentoring_network` | 멘토-멘티 관계·멘토링 체인 | "김철수의 멘티는 누구야?" |
| `certificate_search` | 자격증 보유자·집계 | "정보처리기사 보유자 목록" |
| `path_analysis` | 두 사람 간 연결 경로 | "김철수와 박지우는 어떻게 연결돼?" |
| `ontology_update` | 채팅으로 온톨로지 개념·동의어 추가 | "LangGraph를 스킬로 추가해줘" |
| `global_analysis` | 전사 거시 분석 (스킬 분포, 수요-공급 갭) | "전사 스킬 분포 Top 10은?" |

**파이프라인 보조 지능**:
- 개념 확장 (온톨로지 동의어: 파이썬 ↔ Python ↔ Py)
- 한국어 접미사 자동 제거 ("~프로젝트", "~팀" 등)
- 대소문자 무시 매칭 (toLower 강제)
- Multi-hop 쿼리 분해
- 벡터 캐시 (유사 질문 재사용 → 8단계 → 6단계 단축)
- 엔티티 미해결 시 명확화 질문
- Adaptive Ontology — 미해결 용어를 백그라운드 학습해 온톨로지 제안 자동 생성

---

## 3. 부가 시스템

| 시스템 | 사용자 체감 기능 |
|--------|-----------------|
| 인제스천 | CSV/Excel 올리면 LLM이 그래프로 변환해 적재. 비동기 job 추적 |
| 부트스트랩 | 비정형 텍스트 → 트리플(주어-관계-목적어) 추출 → 그래프 스키마 자동 발견·정규화 |
| 온톨로지 워크플로 | 미해결 용어 자동 제안 → Admin에서 승인 → 동의어·계층 즉시 반영 |
| 커뮤니티 분석 (GDS) | 스킬 유사도 기반 자연 팀 클러스터 탐지, 유사 직원, 팀 추천. 원클릭 리프레시 |
| RBAC (데모 모드) | 4역할 접근제어 — admin(전체) / manager(조회+스태핑) / editor(조회+편집) / viewer(조회만). `AUTH_ENABLED=true` 시 JWT 인증 |

---

## 4. API 요약 (`/api/v1`)

| 라우터 | 주요 엔드포인트 |
|--------|----------------|
| query | `POST /query`, `POST /query/stream` (SSE), `GET /health`, `GET /schema` |
| visualization | `POST /subgraph`(N-depth), `POST /community`, `POST /query-result`, `POST /query-path`(Multi-hop 경로), `GET /schema` |
| analytics | `POST /projection/create·/communities/detect·/employees/similar·/team/recommend`, `GET·POST /staffing/*` (projects, find-candidates, plan, budget-analysis, categories) |
| ingest | `POST /upload`, `POST /ingest`(비동기), `GET /ingest/{job_id}` |
| graph (edit) | 노드/엣지 CRUD, `GET /nodes/{id}/impact`(삭제 영향도), `POST /nodes/{id}/impact/rename`(이름변경 영향도), `GET /schema/labels` |
| ontology/admin | 제안 CRUD + `approve/reject/batch-approve/batch-reject`, `GET /stats` |
| ontology | `GET /schema`, `GET /concept/{category}/{name}/style` (읽기 전용) |
| communities | `POST /refresh`(원클릭 전체 파이프라인), `GET /status` |

---

## 5. 대표 시나리오

- **HR 골든셋 20문**: [SCENARIOS.md](SCENARIOS.md) — 부서별 평균 시급, max_projects 초과 배정, market_demand 인력 부족 스킬, 예산 집행률 등
- **그래프 차별화 시나리오 (Tier 1~5)**: [GRAPH_UNIQUE_SCENARIOS.md](GRAPH_UNIQUE_SCENARIOS.md)
  - Tier 1 경로 탐색 (두 사람의 연결, 팀 간 브릿지 인물)
  - Tier 2 그래프 알고리즘 (지식 병목 SPOF, 팀 클러스터)
  - Tier 3 온톨로지 추론 (스킬 전이, 의미 확장 검색)
  - Tier 4 복합 관계 (협업 네트워크 추천, 멘토링 체인 영향력)
  - Tier 5 구조 인사이트 (부서 간 협업 네트워크, 스킬 생태계 맵)

---

## 6. 관련 문서

- 기술 아키텍처: [docs/architecture/01-overview.md](architecture/01-overview.md) 외 9편
- LLM 계층 구조 (2026-07 리팩토링): CLAUDE.md "LLM Layers" 섹션
- 개발 가이드: 저장소 루트 [CLAUDE.md](../CLAUDE.md)
