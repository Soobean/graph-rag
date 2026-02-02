"""
SchemaGenerator 테스트

LLM 기반 스키마 자동 생성 기능을 테스트합니다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bootstrap.models import SchemaProposal
from src.bootstrap.schema_generator import SchemaGenerator
from src.repositories.llm_repository import LLMRepository


@pytest.fixture
def mock_llm():
    """Mock LLM Repository"""
    llm = MagicMock(spec=LLMRepository)
    llm.generate_json = AsyncMock()
    llm.close = AsyncMock()
    return llm


@pytest.fixture
def mock_prompt_manager():
    """Mock PromptManager"""
    pm = MagicMock()
    pm.load_prompt.return_value = {
        "system": "You are a schema expert.",
        "user": "Analyze: {domain_hint} {document_count} {documents}",
    }
    return pm


@pytest.fixture
def schema_generator(mock_llm, mock_prompt_manager):
    """SchemaGenerator with mocks"""
    return SchemaGenerator(
        llm_repository=mock_llm,
        prompt_manager=mock_prompt_manager,
    )


class TestSchemaGenerator:
    """SchemaGenerator 테스트"""

    @pytest.mark.asyncio
    async def test_discover_schema_success(self, schema_generator, mock_llm):
        """스키마 발견 성공 케이스"""
        # LLM 응답 설정
        mock_llm.generate_json.return_value = {
            "node_labels": ["Employee", "Project"],
            "relationship_types": ["WORKS_ON", "MANAGES"],
            "properties": {
                "Employee": ["name", "email"],
                "Project": ["name", "status"],
            },
            "constraints": {"Employee": ["email"]},
            "reasoning": "Based on HR domain patterns",
        }

        sample_docs = [
            "홍길동은 AI 프로젝트에 참여했다.",
            "김영희는 개발팀 소속이다.",
        ]

        result = await schema_generator.discover_schema(
            sample_documents=sample_docs,
            domain_hint="기업 인사",
        )

        assert isinstance(result, SchemaProposal)
        assert "Employee" in result.node_labels
        assert "WORKS_ON" in result.relationship_types
        assert mock_llm.generate_json.called

    @pytest.mark.asyncio
    async def test_discover_schema_empty_docs_raises_error(self, schema_generator):
        """빈 문서 목록은 에러"""
        with pytest.raises(ValueError, match="(?i)at least one"):
            await schema_generator.discover_schema(
                sample_documents=[],
                domain_hint=None,
            )

    @pytest.mark.asyncio
    async def test_discover_schema_no_domain_hint(self, schema_generator, mock_llm):
        """도메인 힌트 없이도 동작"""
        mock_llm.generate_json.return_value = {
            "node_labels": ["Entity"],
            "relationship_types": ["RELATED_TO"],
            "properties": {},
        }

        result = await schema_generator.discover_schema(
            sample_documents=["Some text"],
            domain_hint=None,
        )

        assert isinstance(result, SchemaProposal)

    @pytest.mark.asyncio
    async def test_refine_schema(self, schema_generator, mock_llm):
        """스키마 개선"""
        current_schema = SchemaProposal(
            node_labels=["Employee"],
            relationship_types=["KNOWS"],
            properties={"Employee": ["name"]},
        )

        mock_llm.generate_json.return_value = {
            "node_labels": ["Employee", "Skill"],
            "relationship_types": ["KNOWS", "HAS_SKILL"],
            "properties": {
                "Employee": ["name", "email"],
                "Skill": ["name"],
            },
            "reasoning": "Added Skill based on feedback",
        }

        result = await schema_generator.refine_schema(
            current_schema=current_schema,
            feedback="Skill 노드와 HAS_SKILL 관계를 추가해주세요",
        )

        assert "Skill" in result.node_labels
        assert "HAS_SKILL" in result.relationship_types

    @pytest.mark.asyncio
    async def test_merge_schemas(self, schema_generator, mock_llm):
        """스키마 병합"""
        schemas = [
            SchemaProposal(
                node_labels=["Employee"],
                relationship_types=["KNOWS"],
                properties={},
            ),
            SchemaProposal(
                node_labels=["Project"],
                relationship_types=["WORKS_ON"],
                properties={},
            ),
        ]

        mock_llm.generate_json.return_value = {
            "node_labels": ["Employee", "Project"],
            "relationship_types": ["KNOWS", "WORKS_ON"],
            "properties": {},
            "reasoning": "Merged both schemas",
        }

        result = await schema_generator.merge_schemas(schemas)

        assert "Employee" in result.node_labels
        assert "Project" in result.node_labels

    @pytest.mark.asyncio
    async def test_merge_single_schema_returns_as_is(self, schema_generator):
        """단일 스키마 병합은 그대로 반환"""
        schema = SchemaProposal(
            node_labels=["Test"],
            relationship_types=[],
            properties={},
        )

        result = await schema_generator.merge_schemas([schema])
        assert result == schema

    def test_format_documents_truncation(self, schema_generator):
        """긴 문서 목록 자르기"""
        long_docs = ["x" * 3000 for _ in range(20)]

        formatted = schema_generator._format_documents(long_docs, max_chars=5000)

        assert len(formatted) <= 6000  # Some buffer
        assert "truncated" in formatted or "생략" in formatted

    def test_parse_schema_response(self, schema_generator):
        """응답 파싱"""
        response = {
            "node_labels": ["A", "B"],
            "relationship_types": ["R"],
            "properties": {"A": ["x"]},
            "constraints": {},
            "confidence": 0.85,
            "reasoning": "test",
        }

        result = schema_generator._parse_schema_response(response)

        assert isinstance(result, SchemaProposal)
        assert result.confidence == 0.85
