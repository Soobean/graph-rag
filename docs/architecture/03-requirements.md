# 3. 요구사항 분석

## 3.1 질문 유형 분류 및 그래프 탐색 패턴

| 유형 | 설명 | 예시 질문 | 그래프 탐색 패턴 | 복잡도 |
|------|------|----------|-----------------|--------|
| **A. 인력 추천** | 특정 조건에 맞는 직원 검색 | "Python과 ML 스킬을 가진 시니어 개발자는?" | `(e:Employee)-[:HAS_SKILL]->(s:Skill)` | 중 |
| **B. 프로젝트 매칭** | 프로젝트 요구사항과 인력 매칭 | "AI 프로젝트에 투입 가능한 인력은?" | `(p:Project)-[:REQUIRES]->(s:Skill)<-[:HAS_SKILL]-(e:Employee)` | 중 |
| **C. 관계 탐색** | 노드 간 연결 경로 탐색 | "김철수와 박영희의 업무적 연결고리는?" | `shortestPath((a)-[*]-(b))` | 고 |
| **D. 조직 분석** | 부서/팀 구조 및 역량 분석 | "개발팀의 평균 경력과 보유 스킬 분포는?" | `(d:Department)<-[:BELONGS_TO]-(e:Employee)-[:HAS_SKILL]->(s)` | 중 |
| **E. 멘토링 네트워크** | 멘토-멘티 관계 탐색 | "ML 분야 멘토링 가능한 시니어는?" | `(e:Employee)-[:MENTORS]->(), (e)-[:HAS_SKILL]->(s:Skill)` | 중 |
| **F. 자격증 기반 검색** | 인증/자격 기반 필터링 | "AWS 자격증 보유자 중 프로젝트 미배정자는?" | `(e:Employee)-[:HAS_CERTIFICATE]->(c:Certificate)` | 저 |
| **G. 경로 기반 분석** | 다중 홉 관계 분석 | "A 프로젝트 경험자 중 B 부서로 이동 가능한 인력은?" | Multi-hop traversal | 고 |

---

## 3.2 질문 유형별 상세 탐색 패턴

```cypher
-- [A. 인력 추천 패턴]
MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill)
WHERE s.name IN ['Python', 'ML']
WITH e, COUNT(s) as matchedSkills
WHERE matchedSkills >= 2
OPTIONAL MATCH (e)-[:BELONGS_TO]->(d:Department)
OPTIONAL MATCH (e)-[:HAS_POSITION]->(p:Position)
RETURN e, d, p

-- [B. 프로젝트 매칭 패턴]
MATCH (proj:Project {name: $projectName})-[:REQUIRES]->(s)
WITH proj, COLLECT(s) as requiredSkills
MATCH (e:Employee)-[:HAS_SKILL]->(skill)
WHERE skill IN requiredSkills
WITH e, COUNT(skill) as coverage, SIZE(requiredSkills) as total
RETURN e, coverage * 1.0 / total as matchRate ORDER BY matchRate DESC

-- [C. 관계 탐색 패턴]
MATCH path = shortestPath(
  (a:Employee {name: $name1})-[*..5]-(b:Employee {name: $name2})
)
RETURN path, LENGTH(path) as distance

-- [D. 조직 분석 패턴]
MATCH (d:Department {name: $deptName})<-[:BELONGS_TO]-(e)
OPTIONAL MATCH (e)-[:HAS_SKILL]->(s:Skill)
WITH d, e, COLLECT(s.name) as skills
RETURN d.name, COUNT(e), COLLECT(skills)
```

---

## 3.3 MVP 지원 범위

### MVP에서 지원하는 질문 유형

| 유형 | MVP 지원 | 비고 |
|------|---------|------|
| A. 인력 추천 | ✅ | 핵심 기능 |
| B. 프로젝트 매칭 | ✅ | 단순 매칭만 |
| C. 관계 탐색 | ❌ | Phase 2 |
| D. 조직 분석 | ✅ | 부서별 통계 |
| E. 멘토링 네트워크 | ❌ | Phase 2 |
| F. 자격증 기반 검색 | ✅ | 단순 필터링 |
| G. 경로 기반 분석 | ❌ | Phase 2 |

### Phase 2 확장 계획

- 관계 탐색 (shortestPath, allPaths) - C, G 유형
- 멘토링 네트워크 탐색 - E 유형
- 복합 질문 분해 노드 추가
- 대화 히스토리 (State 확장) ✅ 구현 완료
- 결과 시각화
