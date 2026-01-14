"""
API Routes Package
"""

from src.api.routes.analytics import router as analytics_router
from src.api.routes.ingest import router as ingest_router
from src.api.routes.query import router as query_router

__all__ = ["query_router", "ingest_router", "analytics_router"]
