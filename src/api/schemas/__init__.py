"""
API Schemas Package
"""

from src.api.schemas.analytics import (
    CommunityDetectRequest,
    CommunityDetectResponse,
    CommunityInfo,
    ProjectionStatusResponse,
    SimilarEmployee,
    SimilarEmployeeRequest,
    SimilarEmployeeResponse,
    TeamMember,
    TeamRecommendRequest,
    TeamRecommendResponse,
)
from src.api.schemas.explainability import (
    ConceptExpansionTree,
    ExplainableGraphData,
    ExplainableResponse,
    ThoughtProcessVisualization,
    ThoughtStep,
)
from src.api.schemas.ingest import (
    FileUploadResponse,
    IngestRequest,
    IngestResponse,
    IngestStats,
    IngestStatusResponse,
    SourceType,
)
from src.api.schemas.query import (
    HealthResponse,
    QueryMetadata,
    QueryRequest,
    QueryResponse,
    SchemaResponse,
)
from src.api.schemas.skill_gap import (
    CategoryCoverage,
    CoverageStatus,
    MatchType,
    RecommendedEmployee,
    SkillCategory,
    SkillCategoryListResponse,
    SkillCoverage,
    SkillGapAnalyzeRequest,
    SkillGapAnalyzeResponse,
    SkillMatch,
    SkillRecommendRequest,
    SkillRecommendResponse,
)

__all__ = [
    # Query
    "QueryRequest",
    "QueryResponse",
    "QueryMetadata",
    "HealthResponse",
    "SchemaResponse",
    # Explainability
    "ThoughtStep",
    "ConceptExpansionTree",
    "ThoughtProcessVisualization",
    "ExplainableGraphData",
    "ExplainableResponse",
    # Ingest
    "FileUploadResponse",
    "IngestRequest",
    "IngestResponse",
    "IngestStats",
    "IngestStatusResponse",
    "SourceType",
    # Analytics
    "CommunityDetectRequest",
    "CommunityDetectResponse",
    "CommunityInfo",
    "ProjectionStatusResponse",
    "SimilarEmployee",
    "SimilarEmployeeRequest",
    "SimilarEmployeeResponse",
    "TeamMember",
    "TeamRecommendRequest",
    "TeamRecommendResponse",
    # Skill Gap Analysis
    "CoverageStatus",
    "MatchType",
    "SkillGapAnalyzeRequest",
    "SkillGapAnalyzeResponse",
    "SkillRecommendRequest",
    "SkillRecommendResponse",
    "SkillCoverage",
    "SkillMatch",
    "CategoryCoverage",
    "RecommendedEmployee",
    "SkillCategory",
    "SkillCategoryListResponse",
]
