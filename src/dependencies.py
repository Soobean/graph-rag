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

from src.domain.ontology.registry import OntologyRegistry
from src.graph.pipeline import GraphRAGPipeline
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository
from src.services.gds_service import GDSService
from src.services.ontology_service import OntologyService

if TYPE_CHECKING:
    from src.api.services.explainability import ExplainabilityService
    from src.services.skill_gap_service import SkillGapService

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
# Skill Gap Service 의존성
# ============================================


def get_skill_gap_service(request: Request) -> "SkillGapService":
    """
    SkillGapService 의존성 주입

    main.py lifespan에서 초기화된 인스턴스를 반환합니다.
    """
    return request.app.state.skill_gap_service


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
# 인증 관련 의존성
# ============================================

def get_current_reviewer_id(request: Request) -> str:
    """
    현재 요청자(reviewer)의 ID를 반환

    TODO(Phase 4): JWT/API Key 인증 구현 필요

    Returns:
        str: 현재 요청자 식별자 (현재는 하드코딩)
    """
    return "anonymous_admin"
