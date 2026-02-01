"""
Domain Types

시스템 전반에서 사용되는 TypedDict 정의
dict[str, Any] 대신 명확한 타입을 사용하여 타입 안전성 확보
"""

from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

# =============================================================================
# Graph Schema Types
# =============================================================================


class PropertySchema(TypedDict, total=False):
    """노드/관계 속성 스키마"""

    name: str
    type: str  # e.g., "STRING", "INTEGER", "LIST"
    mandatory: bool


class NodeSchema(TypedDict, total=False):
    """노드 레이블 스키마"""

    label: str
    properties: list[PropertySchema]
    count: int


class RelationshipSchema(TypedDict, total=False):
    """관계 타입 스키마"""

    type: str
    properties: list[PropertySchema]
    start_labels: list[str]
    end_labels: list[str]


class IndexSchema(TypedDict, total=False):
    """인덱스 스키마"""

    name: str
    type: str  # e.g., "BTREE", "FULLTEXT"
    label: str
    properties: list[str]


class ConstraintSchema(TypedDict, total=False):
    """제약조건 스키마"""

    name: str
    type: str  # e.g., "UNIQUE", "EXISTS"
    label: str
    properties: list[str]


class GraphSchema(TypedDict, total=False):
    """Neo4j 그래프 스키마 전체"""

    node_labels: list[str]
    relationship_types: list[str]
    nodes: list[NodeSchema]
    relationships: list[RelationshipSchema]
    indexes: list[IndexSchema]
    constraints: list[ConstraintSchema]


# =============================================================================
# Entity Types
# =============================================================================


class ExtractedEntity(TypedDict):
    """LLM이 추출한 엔티티"""

    type: str  # e.g., "Person", "Skill", "Department"
    value: str  # e.g., "홍길동", "Python", "개발팀"
    normalized: str  # 정규화된 값 (선택)


class ResolvedEntity(TypedDict, total=False):
    """Neo4j에서 매칭된 엔티티"""

    id: str  # Neo4j 5.x elementId() 반환값
    labels: list[str]
    name: str
    properties: dict[str, Any]  # Neo4j 속성은 동적이므로 Any 허용
    match_score: float
    original_value: str


class UnresolvedEntity(TypedDict):
    """
    미해결 엔티티 (Neo4j에서 매칭 실패)
    """

    term: str  # 원본 용어 (예: "LangGraph")
    category: str  # 카테고리 (예: "skills", "Person")
    question: str  # 원본 질문 (증거 데이터)
    timestamp: str  # ISO 8601 타임스탬프


# =============================================================================
# LLM Response Types
# =============================================================================


class IntentClassificationResult(TypedDict):
    """Intent 분류 결과"""

    intent: str
    confidence: float


class EntityExtractionResult(TypedDict):
    """엔티티 추출 결과"""

    entities: list[ExtractedEntity]


class IntentEntityExtractionResult(TypedDict):
    """통합 Intent 분류 + 엔티티 추출 결과 (Latency Optimization)"""

    intent: str
    confidence: float
    entities: list[ExtractedEntity]


class CypherGenerationResult(TypedDict, total=False):
    """Cypher 생성 결과"""

    cypher: str
    parameters: dict[str, Any]  # Cypher 파라미터는 동적
    explanation: str


class PromptTemplate(TypedDict):
    """프롬프트 템플릿"""

    system: str
    user: str


# =============================================================================
# Neo4j Repository Result Types
# =============================================================================


class SubGraphNode(TypedDict):
    """서브그래프 노드 구조"""

    id: int
    labels: list[str]
    properties: dict[str, Any]


class SubGraphRelationship(TypedDict):
    """서브그래프 관계 구조"""

    id: int
    type: str
    start_node_id: int
    end_node_id: int
    properties: dict[str, Any]


class SubGraphResult(TypedDict):
    """서브그래프 조회 결과"""

    nodes: list[SubGraphNode]
    relationships: list[SubGraphRelationship]


# =============================================================================
# Pipeline Result Types
# =============================================================================


class FullState(TypedDict, total=False):
    """Explainability를 위한 상세 상태"""

    original_entities: dict[str, list[str]]
    expanded_entities: dict[str, list[str]]
    expansion_strategy: Literal["strict", "normal", "broad"]
    expansion_count: int
    graph_results: list[dict[str, Any]]


class PipelineMetadata(TypedDict, total=False):
    """파이프라인 실행 메타데이터"""

    intent: str
    intent_confidence: float
    entities: dict[str, list[str]]
    resolved_entities: list[ResolvedEntity]
    cypher_query: str
    cypher_parameters: dict[str, Any]
    result_count: int
    execution_path: list[str]
    query_plan: dict[str, Any] | None
    error: str | None
    _full_state: FullState  # 내부용 상세 상태


class PipelineResult(TypedDict):
    """파이프라인 최종 실행 결과"""

    success: bool
    question: str
    response: str
    metadata: PipelineMetadata
    error: str | None


# =============================================================================
# Node Update Types (각 노드가 반환하는 상태 업데이트)
# =============================================================================


class IntentClassifierUpdate(TypedDict, total=False):
    """IntentClassifier 노드 반환 타입"""

    intent: str
    intent_confidence: float
    execution_path: list[str]
    error: str | None


class EntityExtractorUpdate(TypedDict, total=False):
    """EntityExtractor 노드 반환 타입"""

    entities: dict[str, list[str]]
    execution_path: list[str]
    error: str | None


class IntentEntityExtractorUpdate(TypedDict, total=False):
    """통합 IntentEntityExtractor 노드 반환 타입 (Latency Optimization)"""

    intent: str
    intent_confidence: float
    entities: dict[str, list[str]]
    execution_path: list[str]
    error: str | None


class ConceptExpanderUpdate(TypedDict, total=False):
    """ConceptExpander 노드 반환 타입 (온톨로지 기반 개념 확장)"""

    expanded_entities: dict[str, list[str]]  # 확장된 엔티티 (원본 + 동의어 + 하위개념)
    original_entities: dict[str, list[str]]  # 원본 엔티티 (확장 전)
    expansion_count: int  # 확장된 개념 수
    expansion_strategy: Literal["strict", "normal", "broad"]  # 사용된 확장 전략
    execution_path: list[str]
    error: str | None


class EntityResolverUpdate(TypedDict, total=False):
    """EntityResolver 노드 반환 타입"""

    resolved_entities: list[ResolvedEntity]
    unresolved_entities: list[UnresolvedEntity]  # Adaptive Ontology Phase 1
    execution_path: list[str]
    error: str | None


class CypherGeneratorUpdate(TypedDict, total=False):
    """CypherGenerator 노드 반환 타입"""

    schema: GraphSchema
    cypher_query: str
    cypher_parameters: dict[str, Any]
    execution_path: list[str]
    error: str | None


class GraphExecutorUpdate(TypedDict, total=False):
    """GraphExecutor 노드 반환 타입"""

    graph_results: list[dict[str, Any]]  # Neo4j 결과는 동적
    result_count: int
    execution_path: list[str]
    error: str | None


class ResponseGeneratorUpdate(TypedDict, total=False):
    """ResponseGenerator 노드 반환 타입"""

    response: str
    messages: list["BaseMessage"]
    execution_path: list[str]
    error: str | None


class CacheCheckerUpdate(TypedDict, total=False):
    """CacheChecker 노드 반환 타입"""

    question_embedding: list[float] | None
    cache_hit: bool
    cache_score: float
    skip_generation: bool
    cypher_query: str  # 캐시 히트 시 캐싱된 쿼리
    cypher_parameters: dict[str, Any]  # 캐시 히트 시 캐싱된 파라미터
    execution_path: list[str]
    error: str | None


# Multi-hop Query Types


class QueryHop(TypedDict, total=False):
    """Multi-hop 쿼리의 단일 홉 정보"""

    step: int  # 1, 2, 3...
    description: str  # "Python 스킬 보유자 찾기"
    node_label: str  # "Person", "Skill"
    relationship: str  # "HAS_SKILL", "MENTOR_OF"
    direction: Literal["outgoing", "incoming", "both"]
    filter_condition: str | None  # "name = 'Python'"


class QueryPlan(TypedDict, total=False):
    """Multi-hop 쿼리 분해 계획"""

    is_multi_hop: bool  # Multi-hop 쿼리 여부
    hop_count: int  # 총 홉 수
    hops: list[QueryHop]  # 각 홉 정보
    final_return: str  # 최종 반환 대상 (예: "mentor")
    explanation: str  # 쿼리 해석 설명


class QueryDecomposerUpdate(TypedDict, total=False):
    """QueryDecomposer 노드 반환 타입"""

    query_plan: QueryPlan
    execution_path: list[str]
    error: str | None


class OntologyUpdateHandlerUpdate(TypedDict, total=False):
    """OntologyUpdateHandler 노드 반환 타입 (사용자 주도 온톨로지 업데이트)"""

    response: str
    proposal_id: str | None
    applied: bool
    execution_path: list[str]
    messages: list["BaseMessage"]
    error: str | None


class QueryDecompositionResult(TypedDict, total=False):
    """LLM 쿼리 분해 결과"""

    is_multi_hop: bool
    hop_count: int
    hops: list[QueryHop]
    final_return: str
    explanation: str


# =============================================================================
# Type Aliases
# =============================================================================

# 노드 업데이트 타입 Union (모든 가능한 노드 반환 타입)
NodeUpdate = (
    IntentClassifierUpdate
    | EntityExtractorUpdate
    | IntentEntityExtractorUpdate
    | ConceptExpanderUpdate
    | EntityResolverUpdate
    | CypherGeneratorUpdate
    | GraphExecutorUpdate
    | ResponseGeneratorUpdate
    | CacheCheckerUpdate
    | QueryDecomposerUpdate
    | OntologyUpdateHandlerUpdate
)
