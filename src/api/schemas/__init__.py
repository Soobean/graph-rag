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
from src.api.schemas.staffing import (
    BudgetAnalysisRequest,
    BudgetAnalysisResponse,
    FindCandidatesRequest,
    FindCandidatesResponse,
    SkillCategory,
    SkillCategoryListResponse,
    StaffingPlanRequest,
    StaffingPlanResponse,
    TeamMemberCost,
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
    # Project Staffing
    "FindCandidatesRequest",
    "FindCandidatesResponse",
    "StaffingPlanRequest",
    "StaffingPlanResponse",
    "BudgetAnalysisRequest",
    "BudgetAnalysisResponse",
    "TeamMemberCost",
    "SkillCategory",
    "SkillCategoryListResponse",
]
