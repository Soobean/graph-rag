"""
Graph Edit API - 그래프 데이터 편집

관리자가 웹 UI에서 노드/엣지를 CRUD할 수 있는 9개 엔드포인트를 제공합니다.

엔드포인트:
1. POST   /nodes              - 노드 생성
2. GET    /nodes              - 노드 검색
3. GET    /nodes/{node_id}    - 노드 조회
4. PATCH  /nodes/{node_id}    - 노드 수정
5. DELETE /nodes/{node_id}    - 노드 삭제
6. POST   /edges              - 엣지 생성
7. GET    /edges/{edge_id}    - 엣지 조회
8. DELETE /edges/{edge_id}    - 엣지 삭제
9. GET    /schema/labels      - 스키마 정보
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.schemas.graph_edit import (
    CreateEdgeRequest,
    CreateNodeRequest,
    EdgeResponse,
    NodeDeletionImpactResponse,
    NodeListResponse,
    NodeResponse,
    RenameImpactRequest,
    RenameImpactResponse,
    SchemaInfoResponse,
    UpdateNodeRequest,
)
from src.dependencies import get_graph_edit_service
from src.domain.exceptions import EntityNotFoundError, ValidationError
from src.services.graph_edit_service import (
    DEFAULT_SEARCH_LIMIT,
    GraphEditConflictError,
    GraphEditService,
)

router = APIRouter(prefix="/api/v1/graph", tags=["graph-edit"])


# ============================================
# 노드 CRUD
# ============================================


@router.post("/nodes", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    body: CreateNodeRequest,
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
) -> NodeResponse:
    """노드 생성"""
    try:
        result = await service.create_node(body.label, body.properties)
        return NodeResponse(**result)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
    except GraphEditConflictError as e:
        raise HTTPException(status_code=409, detail=e.message) from e


@router.get("/nodes", response_model=NodeListResponse)
async def search_nodes(
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
    label: str | None = Query(default=None, description="레이블 필터"),
    search: str | None = Query(default=None, description="이름 검색어 (CONTAINS)"),
    limit: int = Query(
        default=DEFAULT_SEARCH_LIMIT, ge=1, le=200, description="최대 결과 수"
    ),
) -> NodeListResponse:
    """노드 검색 (레이블, 이름 필터)"""
    try:
        results = await service.search_nodes(label=label, search=search, limit=limit)
        nodes = [NodeResponse(**r) for r in results]
        return NodeListResponse(nodes=nodes, count=len(nodes))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.get("/nodes/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: str,
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
) -> NodeResponse:
    """노드 조회"""
    try:
        result = await service.get_node(node_id)
        return NodeResponse(**result)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e


@router.patch("/nodes/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: str,
    body: UpdateNodeRequest,
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
) -> NodeResponse:
    """노드 속성 수정 (null 값은 속성 삭제)"""
    try:
        result = await service.update_node(node_id, body.properties)
        return NodeResponse(**result)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
    except GraphEditConflictError as e:
        raise HTTPException(status_code=409, detail=e.message) from e


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: str,
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
    force: bool = Query(
        default=False, description="관계가 있어도 삭제 (DETACH DELETE)"
    ),
) -> None:
    """노드 삭제"""
    try:
        await service.delete_node(node_id, force=force)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except GraphEditConflictError as e:
        raise HTTPException(status_code=409, detail=e.message) from e


# ============================================
# Impact Analysis (읽기 전용)
# ============================================


@router.get(
    "/nodes/{node_id}/impact",
    response_model=NodeDeletionImpactResponse,
)
async def get_deletion_impact(
    node_id: str,
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
) -> NodeDeletionImpactResponse:
    """노드 삭제 영향 미리보기 (dry-run, 읽기 전용)"""
    try:
        result = await service.analyze_deletion_impact(node_id)
        return NodeDeletionImpactResponse(**result)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e


@router.post(
    "/nodes/{node_id}/impact/rename",
    response_model=RenameImpactResponse,
)
async def get_rename_impact(
    node_id: str,
    body: RenameImpactRequest,
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
) -> RenameImpactResponse:
    """이름 변경 영향 미리보기 (dry-run, 읽기 전용)"""
    try:
        result = await service.analyze_rename_impact(node_id, body.new_name)
        return RenameImpactResponse(**result)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


# ============================================
# 엣지 CRUD
# ============================================


@router.post("/edges", response_model=EdgeResponse, status_code=status.HTTP_201_CREATED)
async def create_edge(
    body: CreateEdgeRequest,
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
) -> EdgeResponse:
    """엣지 생성"""
    try:
        result = await service.create_edge(
            body.source_id, body.target_id, body.relationship_type, body.properties
        )
        return EdgeResponse(
            id=result["id"],
            type=result["type"],
            source_id=result["source_id"],
            target_id=result["target_id"],
            properties=result["properties"],
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
    except GraphEditConflictError as e:
        raise HTTPException(status_code=409, detail=e.message) from e


@router.get("/edges/{edge_id}", response_model=EdgeResponse)
async def get_edge(
    edge_id: str,
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
) -> EdgeResponse:
    """엣지 조회"""
    try:
        result = await service.get_edge(edge_id)
        return EdgeResponse(
            id=result["id"],
            type=result["type"],
            source_id=result["source_id"],
            target_id=result["target_id"],
            properties=result["properties"],
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e


@router.delete("/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    edge_id: str,
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
) -> None:
    """엣지 삭제"""
    try:
        await service.delete_edge(edge_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e


# ============================================
# 스키마 정보
# ============================================


@router.get("/schema/labels", response_model=SchemaInfoResponse)
async def get_schema_labels(
    service: Annotated[GraphEditService, Depends(get_graph_edit_service)],
) -> SchemaInfoResponse:
    """편집 UI용 스키마 정보 (허용 레이블, 필수 속성, 관계 조합)"""
    result = await service.get_schema_info()
    return SchemaInfoResponse(**result)
