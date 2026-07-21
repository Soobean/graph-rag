"""
LLM Repository 단위 테스트 (task 계층 — 포맷팅/고수준 메서드)

전송 계층(generate/generate_json/fallback/스트리밍/에러분류) 테스트는
tests/infrastructure/test_llm_gateway.py로 이관됨.

실행 방법:
    pytest tests/test_llm_repository.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.llm_repository import LLMRepository


class TestFormatHelpers:
    """포맷팅 헬퍼 메서드 테스트"""

    @pytest.fixture
    def repo(self):
        mock_settings = MagicMock()
        return LLMRepository(mock_settings)

    def test_format_schema_full(self, repo):
        """전체 스키마 포맷팅"""
        schema = {
            "node_labels": ["Employee", "Company"],
            "relationship_types": ["WORKS_AT", "KNOWS"],
        }
        result = repo._format_schema(schema)

        assert "Node Labels: Employee, Company" in result
        assert "Relationship Types: WORKS_AT, KNOWS" in result

    def test_format_schema_empty(self, repo):
        """빈 스키마 포맷팅"""
        result = repo._format_schema({})
        assert result == "Schema information not available"

    def test_format_schema_partial(self, repo):
        """부분 스키마 포맷팅"""
        schema = {"node_labels": ["Employee"]}
        result = repo._format_schema(schema)

        assert "Node Labels: Employee" in result
        assert "Relationship Types" not in result

    def test_format_schema_with_properties(self, repo):
        """속성 정보 포함 스키마 포맷팅"""
        schema = {
            "node_labels": ["Employee", "Project"],
            "relationship_types": ["WORKS_ON"],
            "nodes": [
                {
                    "label": "Employee",
                    "properties": [
                        {"name": "name"},
                        {"name": "department"},
                        {"name": "years_experience"},
                    ],
                },
                {
                    "label": "Project",
                    "properties": [
                        {"name": "name"},
                        {"name": "status"},
                        {"name": "budget_million"},
                    ],
                },
            ],
            "relationships": [
                {
                    "type": "WORKS_ON",
                    "properties": [
                        {"name": "role"},
                        {"name": "allocated_hours"},
                        {"name": "actual_hours"},
                    ],
                },
            ],
        }
        result = repo._format_schema(schema)

        # nodes 필드가 있으면 속성 포함 형식 사용
        assert "Employee (name, department, years_experience)" in result
        assert "Project (name, status, budget_million)" in result
        assert "WORKS_ON (role, allocated_hours, actual_hours)" in result
        # 기존 Node Labels 형식은 사용하지 않아야 함
        assert "Node Labels:" not in result

    def test_format_schema_with_properties_fallback(self, repo):
        """nodes 필드 없으면 기존 label 형식으로 fallback"""
        schema = {
            "node_labels": ["Employee", "Project"],
            "relationship_types": ["WORKS_ON"],
        }
        result = repo._format_schema(schema)

        assert "Node Labels: Employee, Project" in result
        assert "Relationship Types: WORKS_ON" in result

    def test_format_schema_with_empty_properties(self, repo):
        """속성이 빈 노드 스키마"""
        schema = {
            "nodes": [{"label": "Employee", "properties": []}],
            "relationships": [],
        }
        result = repo._format_schema(schema)
        assert "Employee" in result

    def test_format_entities_with_data(self, repo):
        """엔티티 포맷팅"""
        entities = [
            {"type": "Employee", "value": "홍길동", "normalized": "홍길동"},
            {"type": "Company", "value": "ABC회사", "normalized": "ABC"},
        ]
        result = repo._format_entities(entities)

        assert "Employee: 홍길동" in result
        assert "Company: ABC회사" in result

    def test_format_entities_empty(self, repo):
        """빈 엔티티 포맷팅"""
        result = repo._format_entities([])
        assert result == "No entities extracted"

    def test_format_entities_missing_fields(self, repo):
        """필드 누락 엔티티 포맷팅"""
        entities = [{"type": "Employee"}]
        result = repo._format_entities(entities)
        assert "Employee:" in result
        assert "Unknown" not in result

    def test_format_results_with_data(self, repo):
        """결과 포맷팅 - row 단위 노드 표현"""
        # _format_results는 Neo4j 노드 형식(labels 속성)을 기대함
        results = [
            {"n": {"id": 1, "labels": ["Employee"], "properties": {"name": "홍길동"}}},
            {"n": {"id": 2, "labels": ["Employee"], "properties": {"name": "김철수"}}},
        ]
        result = repo._format_results(results)

        # 노드 이름 + 라벨이 row 단위로 표시
        assert "홍길동" in result
        assert "김철수" in result
        assert "Employee" in result
        # 헤더 통계에 노드 개수 표시
        assert "Employee=2" in result
        # 총 행 수 표시
        assert "총 2행" in result

    def test_format_results_empty(self, repo):
        """빈 결과 포맷팅"""
        result = repo._format_results([])
        assert result == "No results found"

    def test_format_results_truncation(self, repo):
        """결과가 row 표시 한도(60) 초과 시 자르기"""
        # MAX_PAIR_ROWS = 60 (구현 상수와 일치)
        results = [
            {
                "n": {
                    "id": i + 1,
                    "labels": ["Node"],
                    "properties": {"name": f"Node{i + 1}"},
                }
            }
            for i in range(80)
        ]
        result = repo._format_results(results)

        # 전체 행 수는 통계로 표시
        assert "총 80행" in result
        assert "Node=80" in result
        # 60행 초과분은 "외 N개 행" 안내
        assert "외 20개 행" in result

    def test_format_results_scalar(self, repo):
        """스칼라(집계) 결과 포맷팅"""
        results = [
            {
                "employee": "김철수",
                "project": "챗봇 리뉴얼",
                "allocated": 100,
                "actual": 160,
                "gap": 60,
            },
            {
                "employee": "이영희",
                "project": "데이터레이크",
                "allocated": 80,
                "actual": 120,
                "gap": 40,
            },
            {
                "employee": "박지우",
                "project": "API 플랫폼",
                "allocated": 120,
                "actual": 130,
                "gap": 10,
            },
        ]
        result = repo._format_results(results)

        assert "집계 결과 (3행)" in result
        assert "employee=김철수" in result
        assert "gap=60" in result
        assert "employee=이영희" in result
        assert "employee=박지우" in result

    def test_format_results_scalar_truncation(self, repo):
        """스칼라 결과 30개 초과 시 자르기"""
        # 새 구현은 최대 30행까지 표시
        results = [{"name": f"Person{i}", "count": i} for i in range(35)]
        result = repo._format_results(results)

        assert "집계 결과 (35행)" in result
        assert "외 5개" in result

    def test_format_results_mixed(self, repo):
        """노드 + 스칼라 혼합 결과"""
        results = [
            # 노드 결과
            {"n": {"id": 1, "labels": ["Employee"], "properties": {"name": "김철수"}}},
            # 스칼라 결과
            {"total_count": 5, "avg_hours": 120.5},
        ]
        result = repo._format_results(results)

        # 노드 row 표시
        assert "김철수" in result
        assert "Employee" in result
        # 스칼라 집계 별도 표시
        assert "집계 결과 (1행)" in result
        assert "total_count=5" in result
        assert "avg_hours=120.5" in result

    def test_format_results_scalar_null_values(self, repo):
        """스칼라 결과에서 None 값 필터링"""
        results = [
            {"name": "김철수", "value": 10, "extra": None},
        ]
        result = repo._format_results(results)

        assert "name=김철수" in result
        assert "value=10" in result
        assert "extra" not in result

    def test_format_results_preserves_pairs_across_rows(self, repo):
        """
        회귀 방지 테스트 (2026-05-21): 각 row의 (노드, 관계, 노드) 페어가 보존되는지 검증

        Cypher: MATCH (e:Employee)-[r:HAS_SKILL]->(s:Skill) RETURN e, r, s
        같은 사람이 여러 스킬을 가져도 라벨별 합치기가 아닌 row 단위로 표시되어야 한다.
        """
        results = [
            {
                "e": {
                    "id": "n1",
                    "labels": ["Employee"],
                    "properties": {"name": "안시은"},
                },
                "r": {
                    "id": "r1",
                    "type": "HAS_SKILL",
                    "startNodeId": "n1",
                    "endNodeId": "n100",
                    "properties": {"proficiency": "고급"},
                },
                "s": {
                    "id": "n100",
                    "labels": ["Skill"],
                    "properties": {"name": "Pinecone"},
                },
            },
            {
                "e": {
                    "id": "n2",
                    "labels": ["Employee"],
                    "properties": {"name": "류채원"},
                },
                "r": {
                    "id": "r2",
                    "type": "HAS_SKILL",
                    "startNodeId": "n2",
                    "endNodeId": "n101",
                    "properties": {"proficiency": "중급"},
                },
                "s": {
                    "id": "n101",
                    "labels": ["Skill"],
                    "properties": {"name": "Kubeflow"},
                },
            },
            {
                # 같은 사람(안시은)이 다른 스킬을 가진 row — 페어가 분리되어야 함
                "e": {
                    "id": "n1",
                    "labels": ["Employee"],
                    "properties": {"name": "안시은"},
                },
                "r": {
                    "id": "r3",
                    "type": "HAS_SKILL",
                    "startNodeId": "n1",
                    "endNodeId": "n102",
                    "properties": {"proficiency": "초급"},
                },
                "s": {
                    "id": "n102",
                    "labels": ["Skill"],
                    "properties": {"name": "Angular"},
                },
            },
        ]
        result = repo._format_results(results)

        # 헤더: 노드 중복 제거된 카운트 (안시은 중복은 1로 카운트)
        assert "Employee=2" in result  # 안시은, 류채원 (안시은 2번 등장하지만 1로)
        assert "Skill=3" in result
        assert "HAS_SKILL=3" in result

        # row 단위 페어 보존 검증 — 각 사실이 분리된 row로 표시되어야 함
        lines = result.split("\n")
        row_lines = [line for line in lines if line.startswith(("1.", "2.", "3."))]
        assert len(row_lines) == 3

        # 페어 정확성: 안시은-Pinecone-고급, 류채원-Kubeflow-중급, 안시은-Angular-초급
        row1 = next(line for line in row_lines if line.startswith("1."))
        assert "안시은" in row1 and "Pinecone" in row1 and "고급" in row1

        row2 = next(line for line in row_lines if line.startswith("2."))
        assert "류채원" in row2 and "Kubeflow" in row2 and "중급" in row2

        row3 = next(line for line in row_lines if line.startswith("3."))
        assert "안시은" in row3 and "Angular" in row3 and "초급" in row3

        # 페어 손실 회귀 방지: 한 row에 두 스킬이 합쳐서 들어가면 안 됨
        assert "Pinecone, Kubeflow" not in result
        assert "Pinecone, Angular" not in result

    def test_format_results_skip_props_filtered(self, repo):
        """embedding/vector/id 같은 SKIP_PROPS는 LLM 프롬프트에서 제외"""
        results = [
            {
                "n": {
                    "id": "n1",
                    "labels": ["Employee"],
                    "properties": {
                        "name": "홍길동",
                        "department": "AI팀",
                        "embedding": [0.1, 0.2, 0.3],  # 노출 금지
                        "vector": [1, 2, 3],  # 노출 금지
                    },
                }
            }
        ]
        result = repo._format_results(results)

        assert "홍길동" in result
        assert "AI팀" in result
        # 임베딩/벡터 데이터는 LLM에 전달되지 않음
        assert "embedding" not in result
        assert "0.1" not in result
        assert "vector" not in result


class TestHighLevelMethods:
    """고수준 메서드 테스트 (generate_cypher, generate_response 등)"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.azure_openai_endpoint = "https://test.openai.azure.com"
        settings.azure_openai_api_key = "test-key"
        settings.azure_openai_api_version = "2024-10-21"
        settings.light_model_deployment = "gpt-4o-mini"
        settings.heavy_model_deployment = "gpt-4o"
        settings.llm_temperature = 0.0
        settings.llm_max_tokens = 2000
        return settings

    @pytest.mark.asyncio
    async def test_generate_cypher(self, mock_settings):
        """Cypher 쿼리 생성"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"cypher": "MATCH (p:Employee {name: $name}) RETURN p", '
            '"parameters": {"name": "홍길동"}, '
            '"explanation": "Finding person by name"}'
        )

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._gateway._client = mock_client

        result = await repo.generate_cypher(
            question="홍길동 찾아줘",
            schema={"node_labels": ["Employee"], "relationship_types": []},
            entities=[{"type": "Employee", "value": "홍길동", "normalized": "홍길동"}],
        )

        assert "cypher" in result
        assert "parameters" in result
        # HEAVY 모델 사용 확인
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_generate_response(self, mock_settings):
        """응답 생성"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "홍길동은 ABC 회사에서 근무합니다."

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._gateway._client = mock_client

        result = await repo.generate_response(
            question="홍길동이 어디서 일해?",
            query_results=[{"name": "홍길동", "company": "ABC"}],
            cypher_query="MATCH (p:Employee)-[:WORKS_AT]->(c:Company) RETURN p, c",
        )

        assert "홍길동" in result
        assert "ABC" in result

