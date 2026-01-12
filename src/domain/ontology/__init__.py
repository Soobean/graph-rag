"""
Ontology Module

온톨로지 스키마 및 동의어 사전 관리
- schema.yaml: 개념 계층 정의
- synonyms.yaml: 동의어 사전
- loader.py: YAML 로더 및 조회 API

Phase 3 추가:
- ExpansionStrategy: 컨텍스트 기반 확장 전략 (STRICT/NORMAL/BROAD)
- get_strategy_for_intent: Intent와 신뢰도 기반 전략 결정
- get_config_for_strategy: 전략에 맞는 ExpansionConfig 반환
"""

from src.domain.ontology.loader import (
    DEFAULT_EXPANSION_CONFIG,
    INTENT_STRATEGY_MAP,
    ExpansionConfig,
    ExpansionStrategy,
    OntologyLoader,
    get_config_for_strategy,
    get_ontology_loader,
    get_strategy_for_intent,
)

__all__ = [
    # Core
    "OntologyLoader",
    "get_ontology_loader",
    # Expansion Config
    "ExpansionConfig",
    "DEFAULT_EXPANSION_CONFIG",
    # Expansion Strategy (Phase 3)
    "ExpansionStrategy",
    "INTENT_STRATEGY_MAP",
    "get_strategy_for_intent",
    "get_config_for_strategy",
]
