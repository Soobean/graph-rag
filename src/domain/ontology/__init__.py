"""
Ontology Module

온톨로지 스키마 및 동의어 사전 관리
- schema.yaml: 개념 계층 정의
- synonyms.yaml: 동의어 사전
- loader.py: YAML 로더 및 조회 API
"""

from src.domain.ontology.loader import (
    DEFAULT_EXPANSION_CONFIG,
    ExpansionConfig,
    OntologyLoader,
    get_ontology_loader,
)

__all__ = [
    "OntologyLoader",
    "get_ontology_loader",
    "ExpansionConfig",
    "DEFAULT_EXPANSION_CONFIG",
]
