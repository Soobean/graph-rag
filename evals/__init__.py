"""
Eval Harness — 골든셋 자동 평가

목적: 코드와 무관한 정답(oracle)으로 "답이 맞았는가"를 채점한다.
mock 테스트(계약/배선 검증)와 달리, 이 층의 정답은 다음에서만 나온다:
- 사람이 스키마 문서로부터 작성·검증한 reference Cypher (비순환 oracle)
- 도메인 지식으로 큐레이션한 기대 intent / 필수 포함값
- 실제 Neo4j 실행 결과

실행: uv run python -m evals.runner  (docs/EVALS.md 참고)
"""
