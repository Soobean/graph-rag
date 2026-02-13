"""
API Package
"""

from .routes.analytics import router as analytics_router
from .routes.community_admin import router as community_admin_router
from .routes.graph_edit import router as graph_edit_router
from .routes.ingest import router as ingest_router
from .routes.ontology import router as ontology_router
from .routes.ontology_admin import router as ontology_admin_router
from .routes.query import router as query_router
from .routes.visualization import router as visualization_router

__all__ = [
    "query_router",
    "ingest_router",
    "analytics_router",
    "community_admin_router",
    "visualization_router",
    "ontology_router",
    "ontology_admin_router",
    "graph_edit_router",
]
