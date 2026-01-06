"""
도메인 예외 정의

애플리케이션 전역에서 사용되는 커스텀 예외 클래스를 정의합니다.
각 예외는 명확한 의미를 가지며, 에러 핸들링에 활용됩니다.
"""


class GraphRAGError(Exception):
    """Graph RAG 애플리케이션 기본 예외"""

    def __init__(self, message: str, code: str = "UNKNOWN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


# ============================================
# 데이터베이스 관련 예외
# ============================================


class DatabaseError(GraphRAGError):
    """데이터베이스 관련 기본 예외"""

    def __init__(self, message: str, code: str = "DATABASE_ERROR"):
        super().__init__(message, code)


class DatabaseConnectionError(DatabaseError):
    """데이터베이스 연결 실패"""

    def __init__(self, message: str):
        super().__init__(message, code="DATABASE_CONNECTION_ERROR")


class DatabaseAuthenticationError(DatabaseError):
    """데이터베이스 인증 실패"""

    def __init__(self, message: str):
        super().__init__(message, code="DATABASE_AUTH_ERROR")


class QueryExecutionError(DatabaseError):
    """쿼리 실행 실패"""

    def __init__(self, message: str, query: str = ""):
        self.query = query
        super().__init__(message, code="QUERY_EXECUTION_ERROR")


class EntityNotFoundError(DatabaseError):
    """엔티티를 찾을 수 없음"""

    def __init__(self, entity_type: str, entity_id: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(
            f"{entity_type} with id '{entity_id}' not found",
            code="ENTITY_NOT_FOUND",
        )


# ============================================
# LLM 관련 예외
# ============================================


class LLMError(GraphRAGError):
    """LLM 관련 기본 예외"""

    def __init__(self, message: str, code: str = "LLM_ERROR"):
        super().__init__(message, code)


class LLMConnectionError(LLMError):
    """LLM 서비스 연결 실패"""

    def __init__(self, message: str):
        super().__init__(message, code="LLM_CONNECTION_ERROR")


class LLMRateLimitError(LLMError):
    """LLM API 속도 제한"""

    def __init__(self, message: str, retry_after: int = 0):
        self.retry_after = retry_after
        super().__init__(message, code="LLM_RATE_LIMIT")


class LLMResponseError(LLMError):
    """LLM 응답 처리 실패"""

    def __init__(self, message: str):
        super().__init__(message, code="LLM_RESPONSE_ERROR")


# ============================================
# 파이프라인 관련 예외
# ============================================


class PipelineError(GraphRAGError):
    """파이프라인 실행 관련 예외"""

    def __init__(self, message: str, node: str = "", code: str = "PIPELINE_ERROR"):
        self.node = node
        super().__init__(message, code)


class IntentClassificationError(PipelineError):
    """의도 분류 실패"""

    def __init__(self, message: str):
        super().__init__(message, node="intent_classifier", code="INTENT_ERROR")


class EntityExtractionError(PipelineError):
    """엔티티 추출 실패"""

    def __init__(self, message: str):
        super().__init__(message, node="entity_extractor", code="ENTITY_EXTRACTION_ERROR")


class EntityResolutionError(PipelineError):
    """엔티티 해석 실패"""

    def __init__(self, message: str, unresolved_entities: list[str] = None):
        self.unresolved_entities = unresolved_entities or []
        super().__init__(message, node="entity_resolver", code="ENTITY_RESOLUTION_ERROR")


class CypherGenerationError(PipelineError):
    """Cypher 쿼리 생성 실패"""

    def __init__(self, message: str, generated_query: str = ""):
        self.generated_query = generated_query
        super().__init__(message, node="cypher_generator", code="CYPHER_GENERATION_ERROR")


class EmptyResultError(PipelineError):
    """검색 결과 없음"""

    def __init__(self, message: str = "No results found for the query"):
        super().__init__(message, node="graph_executor", code="EMPTY_RESULT")


# ============================================
# 입력 검증 관련 예외
# ============================================


class ValidationError(GraphRAGError):
    """입력 검증 실패"""

    def __init__(self, message: str, field: str = ""):
        self.field = field
        super().__init__(message, code="VALIDATION_ERROR")


class InvalidQueryError(ValidationError):
    """유효하지 않은 쿼리"""

    def __init__(self, message: str):
        super().__init__(message, field="question")


# ============================================
# 설정 관련 예외
# ============================================


class ConfigurationError(GraphRAGError):
    """설정 오류"""

    def __init__(self, message: str, config_key: str = ""):
        self.config_key = config_key
        super().__init__(message, code="CONFIGURATION_ERROR")
