"""
KG Extractor (LLM Logic)

LLM을 사용하여 텍스트에서 그래프 구조를 추출합니다.
Schema Definition에 따른 Strict Validation을 수행합니다.
"""

import logging

from openai import AsyncAzureOpenAI

from src.config import get_settings
from src.ingestion.models import Document, ExtractedGraph, Node, generate_entity_id
from src.ingestion.schema import NODE_PROPERTIES, VALID_RELATIONS, RelationType

logger = logging.getLogger(__name__)

# Edge confidence threshold - 이 값 미만의 신뢰도를 가진 엣지는 제거됨
EDGE_CONFIDENCE_THRESHOLD = 0.8


class GraphExtractor:
    """
    LLM 기반 그래프 추출기

    특징:
    1. Schema Awareness: 정의된 Schema만 추출하도록 유도
    2. Post-Validation: 추출된 결과 중 비즈니스 규칙 위반 항목 필터링
    3. Confidence Score: 신뢰도가 낮은 추출 결과 제거
    """

    def __init__(self) -> None:
        settings = get_settings()

        # Azure OpenAI 클라이언트 직접 생성 (LangChain 제거)
        self.client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )
        self.deployment_name = settings.heavy_model_deployment

        # Pydantic 모델에서 JSON Schema 추출
        self._json_schema = self._build_json_schema()

    def _build_json_schema(self) -> dict:
        """ExtractedGraph의 JSON Schema 생성"""
        schema = ExtractedGraph.model_json_schema()
        return {
            "name": "extracted_graph",
            "strict": False,  # Dict[str, Any] 지원을 위해 strict=False
            "schema": schema,
        }

    async def extract(self, document: Document) -> ExtractedGraph:
        """
        문서에서 그래프 구조 추출 및 검증 수행
        """
        # 1. Extraction
        try:
            raw_graph = await self._run_llm(document.page_content)
        except Exception as e:
            logger.error(f"LLM Extraction Failed: {e}")
            return ExtractedGraph(nodes=[], edges=[])

        # 2. Post-Processing & Validation
        valid_nodes = []
        valid_edges = []

        # LLM이 생성한 임시 ID → UUID5 ID 매핑
        # (LLM의 임시 ID를 키로, 새 UUID5 ID를 값으로)
        id_mapping: dict[str, str] = {}
        node_map: dict[str, Node] = {}  # 새 UUID5 ID → Node

        for node in raw_graph.nodes:
            # 출처 정보 주입
            node.source_metadata = document.metadata

            # UUID5 기반 결정적 ID 생성 (Natural Key 우선)
            old_id = node.id
            new_id = generate_entity_id(
                label=node.label,
                properties=node.properties,
            )

            # ID 매핑 저장 (엣지 업데이트용)
            id_mapping[old_id] = new_id
            node.id = new_id

            node_map[new_id] = node
            valid_nodes.append(node)

        # 엣지 검증
        for edge in raw_graph.edges:
            # 출처 정보 주입
            edge.source_metadata = document.metadata

            # Rule 1: Confidence Check
            if edge.confidence < EDGE_CONFIDENCE_THRESHOLD:
                logger.warning(
                    f"Dropped low confidence edge ({edge.confidence:.2f}): "
                    f"{edge.source_id} -[{edge.type}]-> {edge.target_id}"
                )
                continue

            # LLM 임시 ID → UUID5 ID 변환
            new_source_id = id_mapping.get(edge.source_id)
            new_target_id = id_mapping.get(edge.target_id)

            if not new_source_id or not new_target_id:
                logger.warning(f"Dropped edge with unmapped IDs: {edge}")
                continue

            # Rule 2: Schema Validation (Source/Target Labels)
            src_node = node_map.get(new_source_id)
            tgt_node = node_map.get(new_target_id)

            if not src_node or not tgt_node:
                logger.warning(f"Dropped edge with missing nodes: {edge}")
                continue

            if not self._is_valid_relation(src_node, tgt_node, edge.type):
                logger.warning(
                    f"Dropped invalid relation: "
                    f"{src_node.label} -[{edge.type}]-> {tgt_node.label}"
                )
                continue

            # Edge ID도 UUID5로 업데이트
            edge.source_id = new_source_id
            edge.target_id = new_target_id

            # Label 정보 주입 (Neo4j 쿼리 최적화용)
            edge.source_label = src_node.label
            edge.target_label = tgt_node.label

            valid_edges.append(edge)

        return ExtractedGraph(nodes=valid_nodes, edges=valid_edges)

    async def _run_llm(self, text: str) -> ExtractedGraph:
        """Azure OpenAI 직접 호출 (LangChain 제거)"""
        response = await self.client.chat.completions.create(
            model=self.deployment_name,
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": self._json_schema,
            },
        )

        # JSON 응답을 Pydantic 모델로 변환
        # 방어적 처리: choices가 비어있을 수 있음 (컨텐츠 필터링 등)
        if not response.choices:
            logger.warning("LLM returned no choices")
            return ExtractedGraph(nodes=[], edges=[])

        content = response.choices[0].message.content
        if not content or not content.strip():
            logger.warning("LLM returned empty content")
            return ExtractedGraph(nodes=[], edges=[])

        return ExtractedGraph.model_validate_json(content)

    def _get_system_prompt(self) -> str:
        """시스템 프롬프트 생성"""
        # Schema 정보를 프롬프트에 주입
        node_rules_str = "\n".join(
            [
                f"- {label.value}: Extract properties {props}"
                for label, props in NODE_PROPERTIES.items()
            ]
        )

        return f"""You are a top-tier Knowledge Graph Engineer.
Target: Extract structured knowledge (Nodes and Edges) from the text.

## STRICT RULES
1. Only extract nodes and relationships defined in the Allowed Schema.
2. Use the original entity name as the temporary ID (system will generate UUID later).
3. Confidence Score: You MUST estimate confidence (0.0 to 1.0) for every edge. Be conservative.
4. If information is ambiguous, assign low confidence.

## ALLOWED NODE SCHEMAS (Properties to extract)
{node_rules_str}

## ALLOWED RELATIONSHIPS
- WORKS_ON: Person -> Project
- HAS_SKILL: Person -> Skill
- BELONGS_TO: Person -> Department
- HAS_POSITION: Person -> Position
- HAS_CERTIFICATE: Person -> Certificate
- MENTORS: Person(Mentor) -> Person(Mentee)
- REQUIRES: Project -> Skill
- OWNED_BY: Project -> Department

Extract as much detail as possible while strictly adhering to these schemas.
Return the result as JSON matching the ExtractedGraph schema."""

    def _is_valid_relation(self, src: Node, tgt: Node, rel_type: RelationType) -> bool:
        """관계 유효성 검사"""
        expected = VALID_RELATIONS.get(rel_type)
        if not expected:
            return False

        expected_src, expected_tgt = expected
        return (src.label == expected_src) and (tgt.label == expected_tgt)
