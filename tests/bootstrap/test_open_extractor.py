"""
OpenExtractor 테스트

Open Information Extraction 기능을 테스트합니다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bootstrap.models import ExtractionResult, SchemaProposal, Triple
from src.bootstrap.open_extractor import OpenExtractor
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
        "system": "You are an extraction expert.",
        "user": "Extract from: {document} {schema_hint}",
    }
    return pm


@pytest.fixture
def extractor(mock_llm, mock_prompt_manager):
    """OpenExtractor with mocks"""
    return OpenExtractor(
        llm_repository=mock_llm,
        prompt_manager=mock_prompt_manager,
    )


class TestOpenExtractor:
    """OpenExtractor 테스트"""

    @pytest.mark.asyncio
    async def test_extract_triples_success(self, extractor, mock_llm):
        """트리플 추출 성공"""
        mock_llm.generate_json.return_value = {
            "triples": [
                {
                    "subject": "홍길동",
                    "relation": "참여했다",
                    "object": "AI 프로젝트",
                    "confidence": 0.95,
                },
                {
                    "subject": "홍길동",
                    "relation": "소속이다",
                    "object": "개발팀",
                    "confidence": 0.90,
                },
            ]
        }

        result = await extractor.extract_triples(
            document="홍길동은 AI 프로젝트에 참여했고 개발팀 소속이다.",
        )

        assert len(result) == 2
        assert result[0].subject == "홍길동"
        assert result[0].relation == "참여했다"
        assert result[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_extract_triples_empty_document(self, extractor):
        """빈 문서는 빈 결과"""
        result = await extractor.extract_triples(document="")
        assert result == []

        result = await extractor.extract_triples(document="   ")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_triples_with_schema_hint(self, extractor, mock_llm):
        """스키마 힌트와 함께 추출"""
        mock_llm.generate_json.return_value = {
            "triples": [
                {
                    "subject": "김영희",
                    "relation": "HAS_SKILL",
                    "object": "Python",
                    "confidence": 0.85,
                }
            ]
        }

        schema = SchemaProposal(
            node_labels=["Person", "Skill"],
            relationship_types=["HAS_SKILL"],
            properties={},
        )

        result = await extractor.extract_triples(
            document="김영희는 Python을 잘한다.",
            schema_hint=schema,
        )

        assert len(result) == 1
        assert result[0].relation == "HAS_SKILL"

    @pytest.mark.asyncio
    async def test_extract_triples_filters_low_confidence(self, extractor, mock_llm):
        """낮은 신뢰도 트리플 필터링"""
        mock_llm.generate_json.return_value = {
            "triples": [
                {"subject": "A", "relation": "R1", "object": "B", "confidence": 0.9},
                {"subject": "C", "relation": "R2", "object": "D", "confidence": 0.3},
            ]
        }

        result = await extractor.extract_triples(
            document="test",
            min_confidence=0.5,
        )

        assert len(result) == 1
        assert result[0].relation == "R1"

    @pytest.mark.asyncio
    async def test_batch_extract(self, extractor, mock_llm):
        """배치 추출"""
        mock_llm.generate_json.return_value = {
            "triples": [
                {"subject": "X", "relation": "Y", "object": "Z", "confidence": 0.8}
            ]
        }

        documents = ["doc1", "doc2"]

        result = await extractor.batch_extract(
            documents=documents,
            batch_size=5,  # 배치 크기를 크게 하여 한번에 처리
        )

        assert isinstance(result, ExtractionResult)
        assert result.document_count == 2

    @pytest.mark.asyncio
    async def test_batch_extract_empty_documents(self, extractor):
        """빈 문서 목록"""
        result = await extractor.batch_extract(documents=[])
        assert isinstance(result, ExtractionResult)
        assert len(result.triples) == 0

    @pytest.mark.asyncio
    async def test_extract_with_chunking(self, extractor, mock_llm):
        """긴 문서 청킹"""
        mock_llm.generate_json.return_value = {
            "triples": [
                {"subject": "A", "relation": "R", "object": "B", "confidence": 0.9}
            ]
        }

        # 청킹 없이 처리 가능한 짧은 문서
        document = "테스트 텍스트입니다. " * 10  # ~150 chars

        result = await extractor.extract_with_chunking(
            document=document,
            chunk_size=2000,  # 문서보다 큰 청크
            overlap=100,
        )

        # 단일 청크로 처리
        assert len(result) >= 1

    def test_format_schema_hint_none(self, extractor):
        """스키마 없을 때 포맷"""
        result = extractor._format_schema_hint(None)
        assert "힌트 없음" in result

    def test_format_schema_hint_with_schema(self, extractor):
        """스키마 있을 때 포맷"""
        schema = SchemaProposal(
            node_labels=["Person", "Skill"],
            relationship_types=["HAS_SKILL"],
            properties={},
        )

        result = extractor._format_schema_hint(schema)
        assert "Person" in result
        assert "HAS_SKILL" in result

    def test_parse_extraction_response_invalid_format(self, extractor):
        """잘못된 응답 형식 처리"""
        result = extractor._parse_extraction_response(
            response={"triples": "not a list"},
            source_text="test",
            min_confidence=0.5,
        )
        assert result == []

    def test_parse_extraction_response_skips_empty_triples(self, extractor):
        """빈 트리플 건너뛰기"""
        result = extractor._parse_extraction_response(
            response={
                "triples": [
                    {"subject": "", "relation": "R", "object": "B", "confidence": 0.9},
                    {"subject": "A", "relation": "R", "object": "B", "confidence": 0.9},
                ]
            },
            source_text="test",
            min_confidence=0.5,
        )
        assert len(result) == 1

    def test_deduplicate_triples(self, extractor):
        """트리플 중복 제거"""
        triples = [
            Triple("A", "R", "B", 0.7, "text1"),
            Triple("A", "R", "B", 0.9, "text2"),  # 중복, 더 높은 confidence
            Triple("C", "R", "D", 0.8, "text3"),
        ]

        result = extractor._deduplicate_triples(triples)

        assert len(result) == 2
        # 높은 confidence가 유지되어야 함
        for t in result:
            if t.subject.lower() == "a":
                assert t.confidence == 0.9
