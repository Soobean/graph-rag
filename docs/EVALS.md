# Eval Harness 운영 가이드

> 골든셋 자동 평가 — "답이 맞았는가"를 코드와 무관한 정답(oracle)으로 채점한다.
> mock 테스트(tests/, 계약·배선·변경 감지)와 역할이 다르다.

## 왜 존재하는가

mock 테스트는 "코드를 보고 코드에 맞춘" 테스트라 품질을 증명하지 못한다 (순환).
이 Harness의 정답은 코드 밖에서 온다:

| 정답의 출처 | 채점 |
|------------|------|
| 사람이 스키마 문서로 작성·검증한 **reference Cypher** | key_set / answer_contains_top / count_match / numeric_close / result_excludes |
| 도메인 지식으로 큐레이션한 기대 intent | intent 허용 리스트 |
| 실제 Neo4j 실행 | 실행 성공 / not_empty |
| LLM judge (선택) | 응답이 조회된 페어에 충실한가 |

모든 지능 개선(프롬프트 수정, self-correcting Cypher 등)은 **개선 전 풀런 →
개선 → 풀런 → 베이스라인 diff**로 전후 비교한다.

## 실행

라이브 Neo4j + Azure OpenAI 필요. CI에 넣지 않는다 (비용·비결정성).

```bash
uv run python -m evals.runner                    # 결정적 채점 풀런 (~5분, ~$0.5)
uv run python -m evals.runner --judge            # + faithfulness (+$0.01)
uv run python -m evals.runner --only q01_dept_avg_rate
uv run python -m evals.runner --limit 5
uv run python -m evals.runner --category org_analysis
uv run python -m evals.runner --verify-refs      # reference만 실행 (LLM 0회, 무료)
uv run python -m evals.runner --baseline evals/baselines/baseline.json  # 회귀 시 exit 1
```

리포트: `evals/reports/eval_<ts>.json` (gitignore). 베이스라인: `evals/baselines/baseline.json` (git 추적, 수동 블레스).

## 골든셋 큐레이션 규칙 (비순환 — 반드시 지킬 것)

1. **reference.cypher는 질문 + `load_to_neo4j.py` 스키마로부터 작성한다.**
   파이프라인이 생성한 Cypher, `src/prompts/cypher_generation.yaml`의 예시를
   복사하면 oracle이 다시 순환된다 — 금지.
2. **인원 집계는 반드시 `e.name` 기준 DISTINCT/그룹.**
   Employee 중복 노드(같은 사람, 여러 노드) 때문에 노드 기준 집계는 오답이다.
   이 규칙 덕에 oracle이 파이프라인의 노드 기준 과소집계를 잡아낸다 (예: q04).
3. **검증 절차**: `--verify-refs`로 행수 + 샘플 3행을 육안 확인한 뒤
   `verified: "YYYY-MM-DD"`를 기록한다. UNVERIFIED reference는 신뢰하지 않는다.
4. **대조는 의미 단위로.** 파이프라인은 같은 답을 다른 행 모양으로 반환할 수
   있으므로 원시 행 비교는 금지 — key_set(값 집합), answer_contains_top(응답
   텍스트), count/numeric(수치), result_excludes(negation 검증)만 사용한다.
   주의: result_excludes는 collect형 응답(엔티티당 전체 속성 목록)에서 제외
   대상이 정당하게 등장할 수 있어 오탐 가능 — 매칭 행 반환형 케이스에만 쓸 것
   (n02에서 실증되어 제거된 사례 참고).
5. **해석 여지가 큰 질문은 reference를 만들지 않는다.**
   "갭이 큰"(절대값? 초과분?) 같은 질문은 oracle이 한 해석을 강요하게 되므로
   tier1 + judge로 커버한다 (예: q18).

## 채점 티어

| 티어 | 대상 | 체크 |
|------|------|------|
| tier0 | 전 26문 | expected_intent(허용 리스트) + 실행 성공 + not_empty |
| tier1 | 판단형 문항 | count_range, must_include_any |
| reference | 15문 (verified) | 위 대조 4종 |
| judge | 판단형·시나리오 9문 | faithfulness — 페어 재조합/무근거 주장 감지 |

`passed`는 tier0+tier1+reference의 AND. judge는 별도 축으로 리포트된다
(응답 품질은 Cypher 정답성과 독립적으로 좋아지거나 나빠질 수 있으므로).

## 케이스 추가 방법

1. `evals/golden_set.yaml`에 케이스 추가 (id 규칙: `q*`=HR 골든셋, `s*`=시나리오, `n*`=negation)
2. 가능하면 reference 작성 (위 규칙 준수) → `--verify-refs` → verified 기록
3. `uv run pytest tests/evals/ -q` (로더 무결성 검사 통과 확인 — 케이스 수 assert 갱신)
4. `--only <id>`로 실측 후 커밋

## 알려진 특성

- **비결정성**: LLM이 실행마다 다른 Cypher를 생성할 수 있어 결과 건수가 흔들린다.
  count_range는 여유 폭으로 두고, 정밀 대조는 reference(자동 추종)에 맡긴다.
- **q17**: 현재 데이터에 agreed_rate < hourly_rate가 0건 — 데이터 재시드 시
  달라질 수 있으며 reference가 자동 추종한다.
- **judge 절단**: graph_results는 60행 샘플로 judge에 전달되고 전체 건수를
  별도 명시한다 (건수 언급 오탐 방지).
