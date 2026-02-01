import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _parse_datetime(value: Any, default: datetime | None = None) -> datetime | None:
    """
    다양한 형식의 datetime 값을 안전하게 파싱

    Args:
        value: 파싱할 값 (str, datetime, Neo4j datetime, None 등)
        default: 파싱 실패 시 반환할 기본값

    Returns:
        파싱된 datetime 또는 default
    """
    if value is None:
        return default

    # 이미 Python datetime인 경우
    if isinstance(value, datetime):
        return value

    # 문자열인 경우 ISO 형식 파싱
    if isinstance(value, str):
        try:
            # 'Z' 접미사 처리 (UTC)
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except ValueError:
            # 민감 데이터 노출 방지: 값 길이만 로깅
            logger.warning(f"Failed to parse datetime string (length={len(value)})")
            return default

    # Neo4j datetime 객체인 경우 (to_native() 메서드 사용)
    if hasattr(value, "to_native"):
        try:
            native_value = value.to_native()
            if isinstance(native_value, datetime):
                return native_value
            return default
        except Exception:
            logger.warning(f"Failed to convert Neo4j datetime: {type(value).__name__}")
            return default

    # 그 외 알 수 없는 타입
    logger.warning(f"Unknown datetime type: {type(value).__name__}")
    return default


class ProposalType(str, Enum):
    """
    온톨로지 변경 제안 유형

    - NEW_CONCEPT: 새로운 개념 추가 (예: "FastAPI"를 skills에 추가)
    - NEW_SYNONYM: 기존 개념의 동의어 추가 (예: "Py" → "Python")
    - NEW_RELATION: 개념 간 관계 추가 (예: "FastAPI" is_child_of "Web Framework")
    """

    NEW_CONCEPT = "NEW_CONCEPT"
    NEW_SYNONYM = "NEW_SYNONYM"
    NEW_RELATION = "NEW_RELATION"


class ProposalStatus(str, Enum):
    """
    온톨로지 변경 제안 상태

    - PENDING: 관리자 검토 대기
    - APPROVED: 관리자가 승인함
    - REJECTED: 관리자가 거부함
    - AUTO_APPROVED: 자동 승인 조건 충족으로 자동 적용됨
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"


class ProposalSource(str, Enum):
    """
    온톨로지 제안 출처

    - CHAT: 사용자가 채팅으로 직접 요청
    - BACKGROUND: 백그라운드 학습 (미해결 엔티티 자동 분석)
    - ADMIN: 관리자가 직접 생성
    """

    CHAT = "chat"
    BACKGROUND = "background"
    ADMIN = "admin"


@dataclass
class OntologyProposal:
    """
    온톨로지 변경 제안

    미해결 엔티티를 LLM이 분석하여 생성한 온톨로지 변경 제안.
    일정 조건 충족 시 자동 승인되거나 관리자 검토를 거쳐 적용됨.

    Attributes:
        id: 고유 식별자 (UUID)
        version: Optimistic Locking용 버전 번호
        proposal_type: 제안 유형 (NEW_CONCEPT, NEW_SYNONYM, NEW_RELATION)
        term: 미해결 용어 (예: "LangGraph")
        category: 카테고리 (예: "skills", "departments")
        suggested_action: LLM이 제안한 액션 설명
        suggested_parent: 부모 개념 (NEW_CONCEPT일 때)
        suggested_canonical: 정규 형태 (NEW_SYNONYM일 때)
        evidence_questions: 이 용어가 등장한 질문 목록
        frequency: 등장 빈도
        confidence: LLM 분석 신뢰도 (0.0 ~ 1.0)
        status: 현재 상태
        created_at: 생성 시각
        updated_at: 마지막 업데이트 시각
        reviewed_at: 검토 완료 시각
        reviewed_by: 검토자 ID
    """

    # 필수 필드
    proposal_type: ProposalType
    term: str
    category: str
    suggested_action: str

    # 선택 필드 (기본값 제공)
    id: str = field(default_factory=lambda: str(uuid4()))
    version: int = 1
    suggested_parent: str | None = None
    suggested_canonical: str | None = None
    evidence_questions: list[str] = field(default_factory=list)
    frequency: int = 1
    confidence: float = 0.0
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    rejection_reason: str | None = None
    # Phase 4: 온톨로지 적용 관련 필드
    suggested_relation_type: str | None = None  # IS_A, SAME_AS, REQUIRES, PART_OF
    applied_at: datetime | None = None  # 온톨로지 실제 적용 시각
    source: ProposalSource = ProposalSource.BACKGROUND  # 제안 출처

    def approve(self, reviewer: str | None = None, auto: bool = False) -> None:
        """제안 승인"""
        self.status = ProposalStatus.AUTO_APPROVED if auto else ProposalStatus.APPROVED
        self.reviewed_at = datetime.now(UTC)
        self.reviewed_by = reviewer or ("system" if auto else None)
        self.updated_at = datetime.now(UTC)
        self.version += 1

    def reject(self, reviewer: str, reason: str | None = None) -> None:
        """제안 거부"""
        self.status = ProposalStatus.REJECTED
        self.reviewed_at = datetime.now(UTC)
        self.reviewed_by = reviewer
        self.rejection_reason = reason
        self.updated_at = datetime.now(UTC)
        self.version += 1

    def can_auto_approve(
        self,
        min_confidence: float = 0.95,
        min_frequency: int = 5,
        allowed_types: list[ProposalType] | None = None,
    ) -> bool:
        """
        자동 승인 조건 확인

        Args:
            min_confidence: 최소 신뢰도 임계값
            min_frequency: 최소 등장 빈도
            allowed_types: 자동 승인 허용 타입 목록

        Returns:
            자동 승인 가능 여부
        """
        if allowed_types is None:
            allowed_types = [ProposalType.NEW_SYNONYM]

        if self.status != ProposalStatus.PENDING:
            return False

        if self.proposal_type not in allowed_types:
            return False

        if self.confidence < min_confidence:
            return False

        if self.frequency < min_frequency:
            return False

        return True

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (Neo4j 저장용)"""
        return {
            "id": self.id,
            "version": self.version,
            "proposal_type": self.proposal_type.value,
            "term": self.term,
            "category": self.category,
            "suggested_action": self.suggested_action,
            "suggested_parent": self.suggested_parent,
            "suggested_canonical": self.suggested_canonical,
            "evidence_questions": self.evidence_questions,
            "frequency": self.frequency,
            "confidence": self.confidence,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "rejection_reason": self.rejection_reason,
            "suggested_relation_type": self.suggested_relation_type,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "source": self.source.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OntologyProposal":
        """딕셔너리에서 복원 (Neo4j 조회용)"""
        now = datetime.now(UTC)
        return cls(
            id=data["id"],
            version=data.get("version", 1),
            proposal_type=ProposalType(data["proposal_type"]),
            term=data["term"],
            category=data["category"],
            suggested_action=data["suggested_action"],
            suggested_parent=data.get("suggested_parent"),
            suggested_canonical=data.get("suggested_canonical"),
            evidence_questions=data.get("evidence_questions") or [],
            frequency=data.get("frequency", 1),
            confidence=data.get("confidence", 0.0),
            status=ProposalStatus(data.get("status", "pending")),
            created_at=_parse_datetime(data.get("created_at"), default=now) or now,
            updated_at=_parse_datetime(data.get("updated_at"), default=now) or now,
            reviewed_at=_parse_datetime(data.get("reviewed_at")),
            reviewed_by=data.get("reviewed_by"),
            rejection_reason=data.get("rejection_reason"),
            suggested_relation_type=data.get("suggested_relation_type"),
            applied_at=_parse_datetime(data.get("applied_at")),
            source=ProposalSource(data.get("source", "background")),
        )
