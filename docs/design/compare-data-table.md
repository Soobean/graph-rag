# CSV 데이터 테이블 구조

> 소스: `data/company_realistic/*.csv`
> 파생 필드 생성: `scripts/enrich_csv.py`
> Neo4j 적재: `load_to_neo4j.py`

---

## 1. Employee 테이블

**파일**: `employees.csv` (1,000건)

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `id` | string | `EMP0001` | PK (UNIQUE) |
| `name` | string | `윤서준` | 이름 (INDEX) |
| `email` | string | `emp0001@techstar.com` | 이메일 |
| `job_type` | string | `보안엔지니어` | 직무 유형 (12종) |
| `years_experience` | int | `2` | 경력 연수 (0~18) |
| `hire_date` | string | `2023-12-02` | 입사일 |
| `position_id` | string | `POS003` | FK → Position |
| `department_id` | string | `DEPT011` | FK → Department |
| `hourly_rate` | int | `66000` | 시간 단가 (원). 파생 필드 |
| `max_projects` | int | `3` | 최대 동시 프로젝트 수. 파생 필드 |
| `department` | string | `보안팀` | 부서명 (비정규화) |

### 파생 필드 (enrich_csv.py)

**hourly_rate** = `base_rate(경력) x job_multiplier`

```
base_rate:       0년=40K, 1년=55K, 3년=70K, 5년=85K, 7년=100K, 10년=120K, 15년+=150K
job_multiplier:  보안=1.20, ML=1.15, 데이터/DevOps/SRE=1.10, 백엔드/풀스택/PM=1.05, UX=0.95
범위: 38,000 ~ 180,000원
```

**max_projects** = 경력 기반 (2~5)

### Neo4j 적재 후 추가 속성

| 속성 | 설명 |
|------|------|
| `availability` | `available` / `partial` / `unavailable`. 활성 프로젝트 수 기반 post-load 계산 |
| `communityId` | GDS Leiden 커뮤니티 ID. post-load 계산 |

### 직무 유형 분포 (12종)

프론트엔드개발자(208), ML엔지니어(200), 백엔드개발자(195), 데이터엔지니어(145), SRE(139), 데이터분석가(130), 풀스택개발자(123), 모바일개발자(103), DevOps엔지니어(98), PM/PO(59), 보안엔지니어(50), UX디자이너(50)

---

## 2. Project 테이블

**파일**: `projects.csv` (150건)

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `id` | string | `PROJ0001` | PK (UNIQUE) |
| `name` | string | `ETL파이프라인 구축` | 프로젝트명 (INDEX) |
| `type` | string | `데이터플랫폼` | 유형 (INDEX) |
| `status` | string | `취소` | 상태 (INDEX) |
| `start_date` | string | `2024-06-28` | 시작일 |
| `budget_million` | int | `9100` | 예산 (백만원, 원본) |
| `dept_id` | string | `DEPT006` | FK → Department |
| `required_skills` | string | `SK001,SK075,...` | 필요 스킬 ID 목록 (쉼표 구분) |
| `budget_allocated` | int | `9100000000` | 배정 예산 (원). 파생: `budget_million x 1,000,000` |
| `budget_spent` | int | `910000000` | 집행 예산 (원). 파생 |
| `duration_months` | int | `12` | 기간 (월). 파생 |
| `estimated_hours` | int | `8000` | 예상 공수 (시간). 파생 |
| `required_headcount` | int | `8` | 필요 인원. 파생 |

### 파생 필드 (enrich_csv.py)

**budget_spent** = `budget_allocated x status별 비율`

| status | 비율 |
|--------|------|
| 완료 | 95% |
| 진행중 | 45% |
| 보류 | 20% |
| 취소 | 10% |
| 계획 | 0% |

**duration_months / estimated_hours / required_headcount** = 예산 규모 기반

| budget_million 범위 | duration | hours | headcount |
|--------------------|----------|-------|-----------|
| < 3000 | 6 | 3,000 | 3 |
| 3000 ~ 7000 | 9 | 5,000 | 5 |
| >= 7000 | 12 | 8,000 | 8 |

### status 분포

진행중 / 완료 / 보류 / 계획 / 취소 (5종)

---

## 3. Skill 테이블

**파일**: `skills.csv` (98건)

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `id` | string | `SK001` | PK (UNIQUE) |
| `name` | string | `Python` | 스킬명 (INDEX) |
| `category` | string | `Language` | 카테고리 (INDEX) |
| `difficulty` | string | `Medium` | 난이도 |
| `hourly_rate_min` | int | `60000` | 시장 최저 단가 (원) |
| `hourly_rate_max` | int | `120000` | 시장 최고 단가 (원) |
| `market_demand` | string | `high` | 시장 수요 |

### 난이도별 단가 범위

| difficulty | hourly_rate_min | hourly_rate_max |
|-----------|-----------------|-----------------|
| Easy | 40,000 | 80,000 |
| Medium | 60,000 | 120,000 |
| Hard | 80,000 | 180,000 |

### 카테고리 (9종)

Language, Framework, Cloud, Database, DevOps, AI, Data, Security, Collaboration

---

## 4. 관계 테이블 (Junction Tables)

### employee_skill.csv (8,525건)

`Employee -[HAS_SKILL]-> Skill`

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `employee_id` | string | `EMP0001` | FK → Employee |
| `skill_id` | string | `SK001` | FK → Skill |
| `proficiency` | string | `초급` | 숙련도: 초급/중급/고급/전문가 |
| `years_used` | int | `1` | 사용 연수 (0~6) |
| `rate_factor` | float | `0.5` | 숙련도 가중치. 파생 |
| `effective_rate` | int | `71100` | 스킬 발휘 시 시장 단가 (원). 파생 |

**rate_factor**: 초급=0.5, 중급=0.7, 고급=0.85, 전문가=1.0

**effective_rate** = `hourly_rate_min + (hourly_rate_max - hourly_rate_min) x rate_factor x (0.3 + 0.7 x years_used / 10)`
- 범위: 46,000 ~ 243,000원

---

### employee_project.csv (2,649건)

`Employee -[WORKS_ON]-> Project`

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `employee_id` | string | `EMP0001` | FK → Employee |
| `project_id` | string | `PROJ0004` | FK → Project |
| `role` | string | `개발자` | 역할: PM/TL/개발자/디자이너/분석가/QA |
| `contribution_percent` | int | `44` | 기여도 % (35~90) |
| `agreed_rate` | int | `66000` | 합의 단가 (원). 참여 시점 Employee.hourly_rate |
| `allocated_hours` | int | `1000` | 배정 공수 (시간). 파생: `estimated_hours / required_headcount` |
| `actual_hours` | int | `500` | 실제 투입 공수 (시간). 파생 |

**actual_hours**: 완료=allocated x 0.95, 진행중=allocated x 0.5, 나머지=0

---

### project_skill.csv (936건)

`Project -[REQUIRES]-> Skill`

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `project_id` | string | `PROJ0001` | FK → Project |
| `skill_id` | string | `SK001` | FK → Skill |
| `importance` | string | `우대` | 중요도: 필수/우대/선택 |
| `required_proficiency` | string | `중급` | 요구 숙련도 |
| `required_headcount` | int | `1` | 필요 인원 |
| `max_hourly_rate` | int | `90000` | 단가 상한 (원) |
| `priority` | int | `2` | 우선순위 |

**importance별 기본값**:

| importance | required_proficiency | required_headcount | max_hourly_rate | priority |
|-----------|---------------------|-------------------|-----------------|----------|
| 필수 | 고급 | 2 | hourly_rate_max | 1 |
| 우대 | 중급 | 1 | avg(min, max) | 2 |
| 선택 | 초급 | 1 | hourly_rate_min | 3 |

### employee_certificate.csv (899건)

`Employee -[HAS_CERTIFICATE]-> Certificate`

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `employee_id` | string | `EMP0001` | FK → Employee |
| `certificate_id` | string | `CERT016` | FK → Certificate |
| `acquired_date` | string | `2025-05-16` | 취득일 |

---

### mentorship.csv (198건)

`Employee -[MENTORS]-> Employee`

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `mentor_id` | string | `EMP0003` | FK → Employee (멘토) |
| `mentee_id` | string | `EMP0113` | FK → Employee (멘티) |
| `start_date` | string | `2025-11-26` | 멘토링 시작일 |

---

## 5. 보조 테이블

### departments.csv (15건)

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `id` | string | `DEPT001` | PK (UNIQUE) |
| `name` | string | `플랫폼개발본부` | 부서명 (INDEX) |
| `head_count` | int | `80` | 인원 수 |
| `budget_billion` | float | `15` | 부서 예산 (십억원) |
| `office_id` | string | `OFF001` | FK → Office |

---

### positions.csv (9건)

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `id` | string | `POS002` | PK (UNIQUE) |
| `name` | string | `사원` | 직급명 (INDEX) |
| `level` | int | `1` | 직급 레벨 |
| `min_years` | int | `0` | 최소 경력 |
| `max_years` | int | `3` | 최대 경력 |

---

### certificates.csv (19건)

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `id` | string | `CERT001` | PK (UNIQUE) |
| `name` | string | `AWS Solutions Architect` | 자격증명 (INDEX) |
| `issuer` | string | `Amazon` | 발급 기관 |
| `category` | string | `Cloud` | 카테고리 |

---

### offices.csv (4건)

| 컬럼 | 타입 | 예시 | 설명 |
|------|------|------|------|
| `id` | string | `OFF001` | PK (UNIQUE) |
| `name` | string | `판교 본사` | 사무실명 (INDEX) |
| `city` | string | `성남` | 도시 |
| `address` | string | `판교역로 235` | 주소 |

---

## 7. 테이블 간 관계도

```
Employee ──HAS_SKILL──▶ Skill ◀──REQUIRES── Project
    │                                           │
    ├──WORKS_ON──▶ Project                      │
    ├──BELONGS_TO──▶ Department ◀──OWNED_BY─────┘
    ├──HAS_POSITION──▶ Position
    ├──HAS_CERTIFICATE──▶ Certificate
    └──MENTORS──▶ Employee
```
