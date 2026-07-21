"""
LLM Infrastructure Package

Azure OpenAI 전송 계층: 클라이언트 관리, primitive 생성, fallback 정책, 임베딩
"""

from src.infrastructure.llm.gateway import (
    FALLBACK_EXCEPTIONS,
    AzureOpenAIGateway,
    ModelTier,
    classify_api_status_error,
)

__all__ = [
    "AzureOpenAIGateway",
    "ModelTier",
    "FALLBACK_EXCEPTIONS",
    "classify_api_status_error",
]
