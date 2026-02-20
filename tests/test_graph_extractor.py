"""
GraphExtractor + IngestionPipeline 단위 테스트

LLM 기반 그래프 추출의 후처리 로직과 Ingestion 파이프라인의
배치 처리 / 에러 핸들링을 검증합니다.

실행: pytest tests/test_graph_extractor.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

from src.ingestion.extractor import EDGE_CONFIDENCE_THRESHOLD, GraphExtractor
from src.ingestion.models import Document, Edge, ExtractedGraph, Node
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.schema import NodeType, RelationType

# ── GraphExtractor ──────────────────────────────────


def _make_document(text: str = "테스트 문서 내용") -> Document:
    """테스트용 Document 팩토리"""
    return Document(
        page_content=text,
        metadata={"source": "test.csv", "row_index": 1},
    )


def _make_node(node_id: str, label: NodeType, **props) -> Node:
    """테스트용 Node 팩토리"""
    return Node(id=node_id, label=label, properties=props)


def _make_edge(
    src: str,
    tgt: str,
    rel_type: RelationType,
    confidence: float = 0.9,
) -> Edge:
    """테스트용 Edge 팩토리"""
    return Edge(
        source_id=src,
        target_id=tgt,
        type=rel_type,
        confidence=confidence,
    )


@patch("src.ingestion.extractor.get_settings")
@patch("src.ingestion.extractor.AsyncAzureOpenAI")
class TestGraphExtractorExtract:
    """GraphExtractor.extract() 후처리 로직 테스트"""

    def _make_extractor(self, MockOpenAI, mock_settings):
        """Mock 주입된 GraphExtractor 생성"""
        settings = MagicMock()
        settings.azure_openai_api_key = "test-key"
        settings.azure_openai_api_version = "2024-02-01"
        settings.azure_openai_endpoint = "https://test.openai.azure.com"
        settings.heavy_model_deployment = "gpt-4o"
        mock_settings.return_value = settings

        extractor = GraphExtractor()
        extractor._run_llm = AsyncMock()
        return extractor

    async def test_extract_id_remapping(self, MockOpenAI, mock_settings):
        """LLM 임시 ID → UUID5 결정적 ID로 변환"""
        extractor = self._make_extractor(MockOpenAI, mock_settings)

        raw = ExtractedGraph(
            nodes=[
                _make_node("홍길동", NodeType.PERSON, name="홍길동"),
                _make_node("Python", NodeType.SKILL, name="Python"),
            ],
            edges=[
                _make_edge("홍길동", "Python", RelationType.HAS_SKILL, 0.95),
            ],
        )
        extractor._run_llm.return_value = raw

        result = await extractor.extract(_make_document())

        # ID가 UUID5 형식으로 변환됨
        assert len(result.nodes) == 2
        for node in result.nodes:
            assert len(node.id) == 36  # UUID format
            assert node.id != "홍길동" and node.id != "Python"

        # 엣지의 source_id/target_id도 UUID5로 변환됨
        assert len(result.edges) == 1
        edge = result.edges[0]
        assert len(edge.source_id) == 36
        assert len(edge.target_id) == 36

    async def test_extract_confidence_filtering(self, MockOpenAI, mock_settings):
        """신뢰도 임계값 미만 엣지 제거"""
        extractor = self._make_extractor(MockOpenAI, mock_settings)

        raw = ExtractedGraph(
            nodes=[
                _make_node("person1", NodeType.PERSON, name="김철수"),
                _make_node("skill1", NodeType.SKILL, name="Python"),
                _make_node("skill2", NodeType.SKILL, name="Java"),
            ],
            edges=[
                _make_edge("person1", "skill1", RelationType.HAS_SKILL, 0.95),  # 통과
                _make_edge("person1", "skill2", RelationType.HAS_SKILL, 0.5),  # 제거
            ],
        )
        extractor._run_llm.return_value = raw

        result = await extractor.extract(_make_document())

        assert len(result.edges) == 1
        # 높은 신뢰도 엣지만 남음
        assert result.edges[0].confidence == 0.95

    async def test_extract_confidence_threshold_boundary(
        self, MockOpenAI, mock_settings
    ):
        """신뢰도 경계값 (0.8) 테스트"""
        extractor = self._make_extractor(MockOpenAI, mock_settings)

        raw = ExtractedGraph(
            nodes=[
                _make_node("p", NodeType.PERSON, name="A"),
                _make_node("s", NodeType.SKILL, name="B"),
            ],
            edges=[
                _make_edge("p", "s", RelationType.HAS_SKILL, EDGE_CONFIDENCE_THRESHOLD),
            ],
        )
        extractor._run_llm.return_value = raw

        result = await extractor.extract(_make_document())

        # 정확히 임계값인 경우: >= 가 아닌 < 비교이므로 통과
        assert len(result.edges) == 1

    async def test_extract_schema_validation(self, MockOpenAI, mock_settings):
        """스키마 위반 관계 제거 (Skill → Person은 불허)"""
        extractor = self._make_extractor(MockOpenAI, mock_settings)

        raw = ExtractedGraph(
            nodes=[
                _make_node("person", NodeType.PERSON, name="김철수"),
                _make_node("skill", NodeType.SKILL, name="Python"),
            ],
            edges=[
                # HAS_SKILL은 Person → Skill 이어야 하는데, 역방향
                _make_edge("skill", "person", RelationType.HAS_SKILL, 0.95),
            ],
        )
        extractor._run_llm.return_value = raw

        result = await extractor.extract(_make_document())

        assert len(result.edges) == 0  # 스키마 위반 → 필터링

    async def test_extract_unmapped_edge_ids_dropped(self, MockOpenAI, mock_settings):
        """엣지의 source/target ID가 노드에 없으면 제거"""
        extractor = self._make_extractor(MockOpenAI, mock_settings)

        raw = ExtractedGraph(
            nodes=[
                _make_node("person", NodeType.PERSON, name="김철수"),
            ],
            edges=[
                # "ghost_node"는 nodes에 없음
                _make_edge("person", "ghost_node", RelationType.HAS_SKILL, 0.95),
            ],
        )
        extractor._run_llm.return_value = raw

        result = await extractor.extract(_make_document())

        assert len(result.edges) == 0

    async def test_extract_source_metadata_injected(self, MockOpenAI, mock_settings):
        """노드/엣지에 source_metadata 주입"""
        extractor = self._make_extractor(MockOpenAI, mock_settings)

        raw = ExtractedGraph(
            nodes=[
                _make_node("p", NodeType.PERSON, name="A"),
                _make_node("s", NodeType.SKILL, name="B"),
            ],
            edges=[
                _make_edge("p", "s", RelationType.HAS_SKILL, 0.9),
            ],
        )
        extractor._run_llm.return_value = raw

        doc = _make_document()
        result = await extractor.extract(doc)

        for node in result.nodes:
            assert node.source_metadata == doc.metadata
        for edge in result.edges:
            assert edge.source_metadata == doc.metadata

    async def test_extract_edge_labels_injected(self, MockOpenAI, mock_settings):
        """엣지에 source_label / target_label 주입"""
        extractor = self._make_extractor(MockOpenAI, mock_settings)

        raw = ExtractedGraph(
            nodes=[
                _make_node("p", NodeType.PERSON, name="A"),
                _make_node("s", NodeType.SKILL, name="B"),
            ],
            edges=[
                _make_edge("p", "s", RelationType.HAS_SKILL, 0.9),
            ],
        )
        extractor._run_llm.return_value = raw

        result = await extractor.extract(_make_document())

        edge = result.edges[0]
        assert edge.source_label == NodeType.PERSON
        assert edge.target_label == NodeType.SKILL

    async def test_extract_llm_error_returns_empty(self, MockOpenAI, mock_settings):
        """LLM 실패 시 빈 그래프 반환"""
        extractor = self._make_extractor(MockOpenAI, mock_settings)
        extractor._run_llm.side_effect = RuntimeError("Azure OpenAI timeout")

        result = await extractor.extract(_make_document())

        assert result.nodes == []
        assert result.edges == []


@patch("src.ingestion.extractor.get_settings")
@patch("src.ingestion.extractor.AsyncAzureOpenAI")
class TestGraphExtractorRunLLM:
    """GraphExtractor._run_llm() 테스트"""

    def _make_extractor(self, MockOpenAI, mock_settings):
        settings = MagicMock()
        settings.azure_openai_api_key = "test-key"
        settings.azure_openai_api_version = "2024-02-01"
        settings.azure_openai_endpoint = "https://test.openai.azure.com"
        settings.heavy_model_deployment = "gpt-4o"
        mock_settings.return_value = settings

        extractor = GraphExtractor()
        return extractor

    async def test_run_llm_empty_choices(self, MockOpenAI, mock_settings):
        """LLM이 choices=[] 반환 시 빈 그래프"""
        extractor = self._make_extractor(MockOpenAI, mock_settings)

        mock_response = MagicMock()
        mock_response.choices = []
        extractor.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await extractor._run_llm("test text")

        assert result.nodes == []
        assert result.edges == []

    async def test_run_llm_empty_content(self, MockOpenAI, mock_settings):
        """LLM이 빈 content 반환 시 빈 그래프"""
        extractor = self._make_extractor(MockOpenAI, mock_settings)

        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        extractor.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await extractor._run_llm("test text")

        assert result.nodes == []
        assert result.edges == []


class TestIsValidRelation:
    """_is_valid_relation() 스키마 검증 테스트"""

    @patch("src.ingestion.extractor.get_settings")
    @patch("src.ingestion.extractor.AsyncAzureOpenAI")
    def test_valid_person_to_skill(self, MockOpenAI, mock_settings):
        """Person → Skill (HAS_SKILL) 유효"""
        mock_settings.return_value = MagicMock(
            azure_openai_api_key="k",
            azure_openai_api_version="v",
            azure_openai_endpoint="e",
            heavy_model_deployment="m",
        )
        extractor = GraphExtractor()
        src = _make_node("p", NodeType.PERSON, name="A")
        tgt = _make_node("s", NodeType.SKILL, name="B")
        assert extractor._is_valid_relation(src, tgt, RelationType.HAS_SKILL) is True

    @patch("src.ingestion.extractor.get_settings")
    @patch("src.ingestion.extractor.AsyncAzureOpenAI")
    def test_invalid_skill_to_person(self, MockOpenAI, mock_settings):
        """Skill → Person (HAS_SKILL) 무효 (역방향)"""
        mock_settings.return_value = MagicMock(
            azure_openai_api_key="k",
            azure_openai_api_version="v",
            azure_openai_endpoint="e",
            heavy_model_deployment="m",
        )
        extractor = GraphExtractor()
        src = _make_node("s", NodeType.SKILL, name="B")
        tgt = _make_node("p", NodeType.PERSON, name="A")
        assert extractor._is_valid_relation(src, tgt, RelationType.HAS_SKILL) is False

    @patch("src.ingestion.extractor.get_settings")
    @patch("src.ingestion.extractor.AsyncAzureOpenAI")
    def test_unknown_relation_type(self, MockOpenAI, mock_settings):
        """정의되지 않은 관계 타입은 무효"""
        mock_settings.return_value = MagicMock(
            azure_openai_api_key="k",
            azure_openai_api_version="v",
            azure_openai_endpoint="e",
            heavy_model_deployment="m",
        )
        extractor = GraphExtractor()
        src = _make_node("p", NodeType.PERSON, name="A")
        tgt = _make_node("s", NodeType.SKILL, name="B")
        # VALID_RELATIONS에 없는 타입 → 기존 VALID_RELATIONS에 없으면 False
        # MENTORS는 Person → Person이어야 하므로 Person → Skill은 무효
        assert extractor._is_valid_relation(src, tgt, RelationType.MENTORS) is False


# ── IngestionPipeline ──────────────────────────────────


class TestIngestionPipeline:
    """IngestionPipeline 배치/에러 처리 테스트"""

    @patch("src.ingestion.pipeline.get_settings")
    @patch("src.ingestion.pipeline.GraphExtractor")
    def test_merge_stats(self, MockExtractor, mock_settings):
        """통계 병합 정확성"""
        mock_settings.return_value = MagicMock(
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
            neo4j_database="neo4j",
        )

        pipeline = IngestionPipeline()

        total = {"total_nodes": 10, "total_edges": 5, "failed_docs": 1}
        batch = {"total_nodes": 3, "total_edges": 2, "failed_docs": 0}

        pipeline._merge_stats(total, batch)

        assert total["total_nodes"] == 13
        assert total["total_edges"] == 7
        assert total["failed_docs"] == 1

    @patch("src.ingestion.pipeline.get_settings")
    @patch("src.ingestion.pipeline.GraphExtractor")
    async def test_process_batch_extraction_failure(self, MockExtractor, mock_settings):
        """배치 내 추출 실패 시 failed_docs 카운트"""
        mock_settings.return_value = MagicMock(
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
            neo4j_database="neo4j",
        )

        pipeline = IngestionPipeline()
        # 추출 실패 시뮬레이션: 하나는 성공, 하나는 실패
        pipeline.extractor.extract = AsyncMock(
            side_effect=[
                ExtractedGraph(
                    nodes=[_make_node("p", NodeType.PERSON, name="A")],
                    edges=[],
                ),
                Exception("LLM error"),
            ]
        )

        mock_client = MagicMock()
        mock_client.execute_write = AsyncMock()
        docs = [_make_document("doc1"), _make_document("doc2")]

        stats = await pipeline._process_batch(mock_client, docs)

        assert stats["failed_docs"] == 1
        assert stats["total_nodes"] == 1

    @patch("src.ingestion.pipeline.get_settings")
    @patch("src.ingestion.pipeline.GraphExtractor")
    async def test_process_batch_empty_results(self, MockExtractor, mock_settings):
        """모든 추출 결과가 빈 경우"""
        mock_settings.return_value = MagicMock(
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
            neo4j_database="neo4j",
        )

        pipeline = IngestionPipeline()
        pipeline.extractor.extract = AsyncMock(
            return_value=ExtractedGraph(nodes=[], edges=[]),
        )

        mock_client = MagicMock()
        mock_client.execute_write = AsyncMock()
        docs = [_make_document()]

        stats = await pipeline._process_batch(mock_client, docs)

        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0
        mock_client.execute_write.assert_not_awaited()  # 저장하지 않음
