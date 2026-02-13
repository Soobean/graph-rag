"""
FastAPI 의존성 주입 모듈

FastAPI의 Depends 패턴을 활용한 의존성 주입을 관리합니다.
- 레이어별 의존성 계층 구조
- 테스트 시 의존성 오버라이드 지원

의존성 흐름:
    Settings -> Infrastructure Clients -> Repositories -> Pipeline -> Services
"""

import logging
from typing import TYPE_CHECKING

from fastapi import Request

from src.auth.models import UserContext
from src.config import get_settings
from src.domain.exceptions import AuthenticationError
from src.domain.ontology.registry import OntologyRegistry
from src.graph.pipeline import GraphRAGPipeline
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository
from src.services.gds_service import GDSService
from src.services.graph_edit_service import GraphEditService
from src.services.ontology_service import OntologyService

if TYPE_CHECKING:
    from src.api.services.explainability import ExplainabilityService
    from src.services.auth_service import AuthService
    from src.services.community_batch_service import CommunityBatchService
    from src.services.project_staffing_service import ProjectStaffingService

logger = logging.getLogger(__name__)


# ============================================
# Infrastructure Layer 의존성
# ============================================

def get_neo4j_client(request: Request) -> Neo4jClient:
    """
    Neo4j 클라이언트 의존성 주입

    main.py lifespan에서 초기화된 app.state.neo4j_client를 반환합니다.
    """
    return request.app.state.neo4j_client


# ============================================
# Repository Layer 의존성
# ============================================

def get_neo4j_repository(request: Request) -> Neo4jRepository:
    """
    Neo4j Repository 의존성 주입

    app.state에서 초기화된 인스턴스를 반환합니다.
    매 요청마다 새 인스턴스를 생성하지 않고 싱글톤을 재사용합니다.
    """
    return request.app.state.neo4j_repo


def get_llm_repository(request: Request) -> LLMRepository:
    """
    LLM Repository 의존성 주입
    app.state에서 초기화된 인스턴스를 가져옵니다.
    """
    return request.app.state.llm_repo


# ============================================
# Graph Pipeline 의존성
# ============================================

def get_graph_pipeline(request: Request) -> GraphRAGPipeline:
    """
    GraphRAG Pipeline 의존성 주입
    app.state에서 초기화된 인스턴스를 가져옵니다.
    """
    return request.app.state.pipeline


# ============================================
# GDS Service 의존성
# ============================================

def get_gds_service(request: Request) -> GDSService:
    """
    GDS Service 의존성 주입
    app.state에서 초기화된 인스턴스를 가져옵니다.
    """
    return request.app.state.gds_service


# ============================================
# Ontology Service 의존성
# ============================================

def get_ontology_service(request: Request) -> OntologyService:
    """
    OntologyService 의존성 주입
    app.state에서 초기화된 인스턴스를 가져옵니다.
    """
    return request.app.state.ontology_service


def get_ontology_registry(request: Request) -> OntologyRegistry:
    """
    OntologyRegistry 의존성 주입

    main.py lifespan에서 초기화된 인스턴스를 반환합니다.
    """
    return request.app.state.ontology_registry


# ============================================
# Graph Edit Service 의존성
# ============================================


def get_graph_edit_service(request: Request) -> GraphEditService:
    """
    GraphEditService 의존성 주입
    app.state에서 초기화된 인스턴스를 가져옵니다.
    """
    return request.app.state.graph_edit_service


# ============================================
# Community Batch Service 의존성
# ============================================


def get_community_batch_service(request: Request) -> "CommunityBatchService":
    """
    CommunityBatchService 의존성 주입
    app.state에서 초기화된 인스턴스를 가져옵니다.
    """
    return request.app.state.community_batch_service


# ============================================
# Project Staffing Service 의존성
# ============================================


def get_staffing_service(request: Request) -> "ProjectStaffingService":
    """
    ProjectStaffingService 의존성 주입

    main.py lifespan에서 초기화된 인스턴스를 반환합니다.
    """
    return request.app.state.staffing_service


# ============================================
# Explainability Service 의존성
# ============================================

def get_explainability_service(request: Request) -> "ExplainabilityService":
    """
    ExplainabilityService 의존성 주입
    app.state에서 초기화된 인스턴스를 가져옵니다.
    """
    return request.app.state.explainability_service


# ============================================
# Auth Service 의존성
# ============================================

def get_auth_service(request: Request) -> "AuthService":
    """AuthService 의존성 주입 (app.state에서 가져옴)"""
    return request.app.state.auth_service


# ============================================
# 인증 관련 의존성
# ============================================

ALLOWED_DEMO_ROLES = {"admin", "manager", "editor", "viewer"}


async def get_current_user(request: Request) -> UserContext:
    """
    현재 요청의 인증된 사용자 컨텍스트를 반환

    AUTH_ENABLED=false (데모/개발 모드):
        X-Demo-Role 헤더 → 데모 UserContext (허용된 역할만)
        헤더 없음 → anonymous_admin (기존 동작 100% 보존)

    AUTH_ENABLED=true (프로덕션):
        X-Demo-Role 무시, Bearer 토큰 필수 → AuthService.get_current_user()

    Raises:
        AuthenticationError: 토큰 없음, 만료, 유효하지 않음
    """
    settings = get_settings()

    # Demo mode: AUTH_ENABLED=false일 때만 X-Demo-Role 허용
    if not settings.auth_enabled:
        demo_role = request.headers.get("X-Demo-Role")
        if demo_role and demo_role in ALLOWED_DEMO_ROLES:
            return UserContext.from_demo_role(demo_role)
        return UserContext.anonymous_admin()

    # Authorization 헤더에서 Bearer 토큰 추출
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid Authorization header")

    token = auth_header[len("Bearer "):]
    if not token:
        raise AuthenticationError("Empty token")

    auth_service: AuthService = request.app.state.auth_service
    return await auth_service.get_current_user(token)


def get_current_reviewer_id(request: Request) -> str:
    """
    현재 요청자(reviewer)의 ID를 반환

    하위 호환성을 위해 유지. 새 코드는 get_current_user()를 사용하세요.
    """
    return "anonymous_admin"
