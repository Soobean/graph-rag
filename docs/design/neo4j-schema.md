# Neo4j 데이터 스키마

> 마지막 업데이트: 2026-02-12
> DB: Neo4j Community 2026.01.3 + GDS Plugin
> 데이터 소스: `data/company_realistic/*.csv` + `scripts/enrich_csv.py` 파생 필드

---

## 1. 노드 (Nodes)

### Employee (1,000)

인력 관리의 핵심 엔티티. 직원 기본 정보 + 파생 필드(단가/가용성).

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| id | string | `EMP0001` | PK (UNIQUE 제약) |
| name | string | `윤서준` | 이름 (INDEX) |
| email | string | `emp0001@techstar.com` | 이메일 |
| job_type | string | `보안엔지니어` | 직무 유형 (12종) |
| years_experience | integer | `2` | 경력 연수 (0~18) |
| hire_date | string | `2023-12-02` | 입사일 |
| hourly_rate | integer | `66000` | **기본 시간 단가** (원). `base_rate(경력) × job_multiplier` |
| max_projects | integer | `3` | 최대 동시 프로젝트 수. 경력 기반 (2~5) |
| department | string | `보안팀` | 소속 부서명 (D3 비정규화) |
| availability | string | `unavailable` | 가용 상태. `available` / `partial` / `unavailable` |
| communityId | integer | `10` | GDS Leiden 커뮤니티 ID (post-load 계산) |

**hourly_rate 결정 로직:**
```
base_rate: 경력 0년=40K, 1년=55K, 3년=70K, 5년=85K, 7년=100K, 10년=120K, 15년+=150K
job_multiplier: 보안=1.20, ML=1.15, 데이터/DevOps/SRE=1.10, 백엔드/풀스택/PM=1.05, UX=0.95, 기타=1.00
hourly_rate = int(base_rate × job_multiplier)
→ 범위: 38,000 ~ 180,000원
```

**availability 결정 로직 (post-load):**
```
활성 프로젝트 = WORKS_ON 중 status IN ['진행중', '계획'] 개수
>= max_projects     → unavailable
>= max_projects - 1 → partial
나머지              → available
→ 분포: available 688 / partial 152 / unavailable 160
```

**12개 직무 유형 분포:**
프론트엔드개발자(208), ML엔지니어(200), 백엔드개발자(195), 데이터엔지니어(145), SRE(139), 데이터분석가(130), 풀스택개발자(123), 모바일개발자(103), DevOps엔지니어(98), PM/PO(59), 보안엔지니어(50), UX디자이너(50)

---

### Skill (98)

기술 스킬. Employee가 HAS_SKILL로 보유, Project가 REQUIRES로 요구.

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| id | string | `SK001` | PK |
| name | string | `Python` | 스킬명 (INDEX) |
| category | string | `Language` | 카테고리 (INDEX). Language/Framework/Cloud/Database/DevOps/AI/Data/Security/Collaboration |
| difficulty | string | `Medium` | 난이도. `Easy` / `Medium` / `Hard` |
| hourly_rate_min | integer | `60000` | 시장 최저 단가. Easy=40K, Medium=60K, Hard=80K |
| hourly_rate_max | integer | `120000` | 시장 최고 단가. Easy=80K, Medium=120K, Hard=180K |
| market_demand | string | `high` | 시장 수요. `high` / `medium` |

---

### Project (150)

프로젝트. 예산/기간/인원 정보 포함.

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| id | string | `PROJ0001` | PK |
| name | string | `ETL파이프라인 구축` | 프로젝트명 (INDEX) |
| type | string | `데이터플랫폼` | 유형 (INDEX) |
| status | string | `취소` | 상태 (INDEX). `진행중` / `완료` / `보류` / `계획` / `취소` |
| start_date | string | `2024-06-28` | 시작일 |
| budget_million | integer | `9100` | 예산 (백만원 단위, CSV 원본) |
| budget_allocated | integer | `9100000000` | 배정 예산 (원). `budget_million × 1,000,000` |
| budget_spent | integer | `910000000` | 집행 예산 (원). status별 비율 |
| duration_months | integer | `12` | 기간 (월). 예산 규모 기반 (6/9/12) |
| estimated_hours | integer | `8000` | 예상 총 공수 (시간). 예산 규모 기반 (3K/5K/8K) |
| required_headcount | integer | `8` | 필요 인원. 예산 규모 기반 (3/5/8) |

**budget_spent 비율:** 완료=95%, 진행중=45%, 보류=20%, 취소=10%, 계획=0%

---

### Department (15)

부서. Employee가 BELONGS_TO, Project가 OWNED_BY로 연결.

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| id | string | `DEPT01` | PK |
| name | string | `보안팀` | 부서명 (INDEX) |
| head_count | integer | `50` | 인원 수 |
| budget_billion | float | `2.5` | 부서 예산 (십억원) |

---

### Position (9)

직급. Employee가 HAS_POSITION으로 연결.

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| id | string | `POS01` | PK |
| name | string | `시니어` | 직급명 (INDEX) |
| level | integer | `3` | 직급 레벨 |
| min_years | integer | `5` | 최소 경력 |
| max_years | integer | `10` | 최대 경력 |

---

### Certificate (19)

자격증. Employee가 HAS_CERTIFICATE로 보유.

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| id | string | `CERT01` | PK |
| name | string | `AWS Solutions Architect` | 자격증명 (INDEX) |
| issuer | string | `Amazon` | 발급 기관 |
| category | string | `Cloud` | 카테고리 |

---

### Office (4)

사무실. Department가 LOCATED_AT으로 연결.

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| id | string | `OFF01` | PK |
| name | string | `본사` | 사무실명 (INDEX) |
| city | string | `서울` | 도시 |
| address | string | `강남구 테헤란로` | 주소 |

---

### Concept (196) — 온톨로지

스킬 계층/동의어를 관리하는 온톨로지 노드. Skill과 직접 관계 없음 (이름으로 브릿지).

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| name | string | `Python` | 개념명 (UNIQUE with type) |
| type | string | `skill` | 유형. `skill`(184) / `subcategory`(8) / `category`(3) |
| description | string | `Skill: Python` | 설명 |
| is_canonical | boolean | `true` | 정규 이름 여부 |
| source | string | `yaml_migration` | 출처 |
| created_at | datetime | | 생성 시각 |
| updated_at | datetime | | 수정 시각 |

**Skill ↔ Concept 브릿지 (중요!):**
```cypher
-- Skill 노드와 Concept 노드 사이에 직접 관계는 없음
-- 이름으로 매칭:
MATCH (s:Skill), (c:Concept)
WHERE toLower(s.name) = toLower(c.name) AND c.type = 'skill'
```

---

## 2. 관계 (Relationships)

### HAS_SKILL (8,525)

`(:Employee)-[:HAS_SKILL]->(:Skill)` — 직원의 스킬 보유

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| proficiency | string | `초급` | 숙련도. `초급` / `중급` / `고급` / `전문가` |
| years_used | integer | `5` | 사용 연수 (0~6) |
| rate_factor | float | `0.5` | 숙련도 가중치. 초급=0.5, 중급=0.7, 고급=0.85, 전문가=1.0 |
| effective_rate | integer | `53000` | **스킬 발휘 시 시장 단가** (원) |

**effective_rate 공식:**
```
effective_rate = int(hourly_rate_min + (hourly_rate_max - hourly_rate_min) × rate_factor × (0.3 + 0.7 × years_used / 10))
→ 범위: 46,000 ~ 243,000원
→ 0.3 base weight: years_used=0이어도 proficiency별 차이 보장
```

---

### WORKS_ON (2,649)

`(:Employee)-[:WORKS_ON]->(:Project)` — 프로젝트 참여

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| role | string | `개발자` | 역할. PM/TL/개발자/디자이너/분석가/QA 등 |
| contribution_percent | integer | `44` | 기여도 (%) (35~90) |
| agreed_rate | integer | `66000` | 합의 단가 (원). 참여 시점의 Employee.hourly_rate |
| allocated_hours | integer | `1000` | 배정 공수 (시간). `estimated_hours / required_headcount` |
| actual_hours | integer | `500` | 실제 투입 공수 (시간). status별 비율 |

**actual_hours 비율:** 완료=allocated×0.95, 진행중=allocated×0.5, 나머지=0

---

### REQUIRES (936)

`(:Project)-[:REQUIRES]->(:Skill)` — 프로젝트의 스킬 요구사항

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| importance | string | `우대` | 중요도. `필수` / `우대` / `선택` |
| required_proficiency | string | `중급` | 요구 숙련도. 필수=고급, 우대=중급, 선택=초급 |
| required_headcount | integer | `1` | 필요 인원. 필수=2, 우대/선택=1 |
| max_hourly_rate | integer | `90000` | 단가 상한 (원). 필수=max, 우대=avg, 선택=min |
| priority | integer | `2` | 우선순위. 필수=1, 우대=2, 선택=3 |

---

### BELONGS_TO (1,000)

`(:Employee)-[:BELONGS_TO]->(:Department)` — 소속 부서. 속성 없음.

### HAS_POSITION (1,000)

`(:Employee)-[:HAS_POSITION]->(:Position)` — 직급. 속성 없음.

### HAS_CERTIFICATE (899)

`(:Employee)-[:HAS_CERTIFICATE]->(:Certificate)` — 자격증 보유

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| acquired_date | string | `2024-03-15` | 취득일 |

### MENTORS (198)

`(:Employee)-[:MENTORS]->(:Employee)` — 멘토-멘티 관계

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| start_date | string | `2024-01-10` | 멘토링 시작일 |

### OWNED_BY (150)

`(:Project)-[:OWNED_BY]->(:Department)` — 프로젝트 소유 부서. 속성 없음.

### LOCATED_AT (15)

`(:Department)-[:LOCATED_AT]->(:Office)` — 부서 위치. 속성 없음.

---

### SIMILAR (19,922) — GDS 생성

`(:Employee)-[:SIMILAR]->(:Employee)` — 스킬 유사도 (Jaccard)

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| similarity | float | `0.45` | Jaccard 유사도 (0.3 이상만 저장) |

**생성 조건:** Node Similarity (GDS), degreeCutoff=3 (최소 3개 공유 스킬), topK=10

> 일반 쿼리에서 SIMILAR 관계 사용 금지. GDS 분석 전용.

---

### IS_A (56) — 온톨로지

`(:Concept)-[:IS_A]->(:Concept)` — 계층 (하위 → 상위)

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| weight | float | `1.0` | 관계 강도 |
| depth | integer | `1` | 계층 깊이 |
| source | string | `schema.yaml` | 출처 |

**계층 구조 예시:**
```
Programming (category)
  ├── Backend (subcategory) → Python, Java, Go, Kotlin, ...
  ├── Frontend (subcategory) → React, Vue.js, Angular, ...
  ├── AI-ML (subcategory) → TensorFlow, PyTorch, ...
  └── Data (subcategory) → Pandas, Apache Spark, ...
Infrastructure (category)
  ├── Cloud (subcategory) → AWS, GCP, Azure
  ├── DevOps (subcategory) → Docker, Kubernetes, ...
  └── Database (subcategory) → PostgreSQL, MongoDB, ...
Collaboration (category)
  └── (직접 스킬) → Jira, Confluence, ...
```

### SAME_AS (139) — 온톨로지

`(:Concept)-[:SAME_AS]->(:Concept)` — 동의어 (alias → canonical)

| 속성 | 타입 | 예시 | 설명 |
|------|------|------|------|
| weight | float | `1.0` | 동의어 강도 |
| source | string | `synonyms.yaml` | 출처 |

**예시:** `파이썬` → `Python`, `K8s` → `Kubernetes`, `스프링` → `Spring Boot`

---

## 3. 접근 제어 매핑

역할별로 볼 수 있는 속성이 다름 (`src/auth/access_policy.py`).

### 노드 속성 가시성

| 라벨 | admin | manager | editor | viewer |
|------|-------|---------|--------|--------|
| Employee | * | * (dept scope) | name, job_type, years_experience, hire_date, availability, max_projects | name, job_type, max_projects |
| Project | * | * (dept scope) | name, type, status, start_date, duration_months, estimated_hours, required_headcount | name, type, status, required_headcount |
| Skill | * | * | * | * |
| Department | * | * | name, head_count | name |
| Position | * | * | * | name, level |
| Certificate | * | * | * | * |
| Office | * | * | * | (접근 불가) |
| Concept | * | (접근 불가) | (접근 불가) | (접근 불가) |

### 관계 속성 가시성

| 관계 | admin/manager | editor | viewer |
|------|--------------|--------|--------|
| HAS_SKILL | * | proficiency, years_used, rate_factor | proficiency, years_used |
| WORKS_ON | * | role, contribution_percent, allocated_hours | role |
| REQUIRES | * | required_proficiency, required_headcount, priority, importance | required_proficiency, priority, importance |
| MENTORS | admin/manager만 접근 | (접근 불가) | (접근 불가) |
| IS_A / SAME_AS | admin만 접근 | (접근 불가) | (접근 불가) |

### D3: 부서 범위

manager만 해당 — Employee, Project에서 자기 부서 데이터만 조회 가능.
나머지 역할은 모든 부서 데이터 접근 가능 (scope=all).

---

## 4. 데이터 통계 요약

```
노드:     1,295 (+ Concept 196 = 1,491)
관계:    15,372 (+ 온톨로지 195 + SIMILAR 19,922 = 35,489)

Employee:   1,000   hourly_rate: 38K~180K (avg 89K)
Skill:         98   difficulty: Easy/Medium/Hard
Project:      150   status: 진행중/완료/보류/계획/취소
Concept:      196   type: skill(184)/subcategory(8)/category(3)

HAS_SKILL:  8,525   effective_rate: 46K~243K (avg 83K)
WORKS_ON:   2,649
REQUIRES:     936
SIMILAR:   19,922   Leiden 커뮤니티: 20개, modularity 0.903
SAME_AS:      139
IS_A:          56
```

---

## 5. CSV → Neo4j 파이프라인

```
[1] data/company_realistic/*.csv         원본 CSV (12개)
        ↓
[2] scripts/enrich_csv.py               파생 필드 계산 → CSV에 기록
        ↓
[3] load_to_neo4j.py                    LOAD CSV → 노드/관계 생성 + availability post-load
        ↓
[4] scripts/migrate_ontology.py         schema.yaml + synonyms.yaml → Concept/IS_A/SAME_AS
        ↓
[5] GDSService                          Node Similarity → SIMILAR + Leiden → communityId
```
