"""
Visualization API Routes

지식 그래프 시각화를 위한 API 엔드포인트
- 서브그래프 조회
- 커뮤니티 그래프
- 스키마 시각화
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemas.visualization import (
    CommunityGraphRequest,
    GraphEdge,
    GraphNode,
    QueryPathVisualizationRequest,
    QueryPathVisualizationResponse,
    QueryResultVisualizationRequest,
    QueryStep,
    SchemaVisualizationResponse,
    SubgraphRequest,
    SubgraphResponse,
)
from src.api.utils.graph_utils import get_node_style, sanitize_props
from src.dependencies import get_graph_pipeline, get_neo4j_repository
from src.domain.validators import validate_cypher_identifier, validate_read_only_cypher
from src.graph.pipeline import GraphRAGPipeline
from src.repositories.neo4j_repository import Neo4jRepository


def _validate_label(label: str) -> str:
    """노드 라벨 검증 (Cypher Injection 방지)"""
    try:
        return validate_cypher_identifier(label, "label")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/visualization", tags=["visualization"])


# ============================================
# 서브그래프 조회
# ============================================


@router.post("/subgraph", response_model=SubgraphResponse)
async def get_subgraph(
    request: SubgraphRequest,
    neo4j: Annotated[Neo4jRepository, Depends(get_neo4j_repository)],
) -> SubgraphResponse:
    """
    노드 중심 서브그래프 조회

    특정 노드를 중심으로 연결된 노드들을 반환합니다.
    vis.js 등의 시각화 라이브러리에서 직접 사용 가능한 형식입니다.
    """
    logger.info(f"Subgraph request: {request}")

    try:
        # 중심 노드 찾기
        if request.node_id:
            center_query = """
            MATCH (n)
            WHERE elementId(n) = $node_id
            RETURN elementId(n) as node_id, labels(n) as labels, properties(n) as props
            """
            center_result = await neo4j.execute_cypher(
                center_query, {"node_id": request.node_id}
            )
        elif request.node_name:
            label_filter = f":{_validate_label(request.node_label)}" if request.node_label else ""
            center_query = f"""
            MATCH (n{label_filter})
            WHERE n.name = $node_name
            RETURN elementId(n) as node_id, labels(n) as labels, properties(n) as props
            LIMIT 1
            """
            center_result = await neo4j.execute_cypher(
                center_query, {"node_name": request.node_name}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="node_id 또는 node_name이 필요합니다.",
            )

        if not center_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="노드를 찾을 수 없습니다.",
            )

        center_props = center_result[0]["props"]
        center_id = center_result[0]["node_id"]
        center_labels = center_result[0]["labels"]

        # 서브그래프 쿼리 (깊이에 따라)
        subgraph_query = f"""
        MATCH path = (center)-[r*1..{request.depth}]-(connected)
        WHERE elementId(center) = $center_id
        WITH center, connected, r, path
        LIMIT {request.limit * 2}
        RETURN DISTINCT
            elementId(center) as center_id,
            elementId(connected) as node_id,
            labels(connected) as labels,
            properties(connected) as props,
            [rel in r | {{
                id: elementId(rel),
                type: type(rel),
                start: elementId(startNode(rel)),
                end: elementId(endNode(rel)),
                props: properties(rel)
            }}] as relationships
        LIMIT {request.limit}
        """

        results = await neo4j.execute_cypher(subgraph_query, {"center_id": center_id})

        # 노드와 엣지 변환
        nodes_map: dict[str, GraphNode] = {}
        edges_map: dict[str, GraphEdge] = {}

        # 중심 노드 추가
        center_style = get_node_style(
            center_labels[0] if center_labels else "", center_props.get("name", "")
        )
        nodes_map[center_id] = GraphNode(
            id=center_id,
            label=center_labels[0] if center_labels else "Node",
            name=center_props.get("name", "Unknown"),
            properties=center_props,
            group=center_labels[0] if center_labels else "default",
            style=center_style,
        )

        for row in results:
            node_id = row["node_id"]
            labels = row["labels"]
            props = row["props"]

            # 노드 추가
            if node_id not in nodes_map:
                # 스타일 조회
                node_style = get_node_style(
                    labels[0] if labels else "", props.get("name", "")
                )

                nodes_map[node_id] = GraphNode(
                    id=node_id,
                    label=labels[0] if labels else "Node",
                    name=props.get("name", "Unknown"),
                    properties=props,
                    group=labels[0] if labels else "default",
                    style=node_style,
                )

            # 엣지 추가
            for rel in row["relationships"]:
                edge_id = rel["id"]
                if edge_id not in edges_map:
                    edges_map[edge_id] = GraphEdge(
                        id=edge_id,
                        source=rel["start"],
                        target=rel["end"],
                        label=rel["type"],
                        properties=rel.get("props", {}),
                    )

        nodes = list(nodes_map.values())
        edges = list(edges_map.values())

        return SubgraphResponse(
            success=True,
            center_node_id=center_id,
            nodes=nodes,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Subgraph query failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"서브그래프 조회 실패: {e}",
        ) from e


# ============================================
# 커뮤니티 그래프
# ============================================


@router.post("/community", response_model=SubgraphResponse)
async def get_community_graph(
    request: CommunityGraphRequest,
    neo4j: Annotated[Neo4jRepository, Depends(get_neo4j_repository)],
) -> SubgraphResponse:
    """
    커뮤니티 그래프 조회

    특정 커뮤니티에 속한 직원들과 그들의 스킬 관계를 반환합니다.
    """
    logger.info(f"Community graph request: community_id={request.community_id}")

    try:
        # 커뮤니티 멤버 조회
        if request.include_skills:
            query = """
            MATCH (e:Employee)
            WHERE e.communityId = $community_id
            OPTIONAL MATCH (e)-[r:HAS_SKILL]->(s:Skill)
            RETURN elementId(e) as emp_id, properties(e) as emp_props,
                   collect({
                       skill_id: elementId(s),
                       skill_props: properties(s),
                       rel_id: elementId(r)
                   }) as skills
            LIMIT $limit
            """
        else:
            query = """
            MATCH (e:Employee)
            WHERE e.communityId = $community_id
            RETURN elementId(e) as emp_id, properties(e) as emp_props, [] as skills
            LIMIT $limit
            """

        results = await neo4j.execute_cypher(
            query,
            {"community_id": request.community_id, "limit": request.limit},
        )

        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"커뮤니티 {request.community_id}를 찾을 수 없습니다.",
            )

        nodes_map: dict[str, GraphNode] = {}
        edges_map: dict[str, GraphEdge] = {}

        for row in results:
            emp_id = row["emp_id"]
            emp_props = row["emp_props"]

            # 직원 노드 추가
            if emp_id not in nodes_map:
                emp_style = get_node_style("Employee")
                nodes_map[emp_id] = GraphNode(
                    id=emp_id,
                    label="Employee",
                    name=emp_props.get("name", "Unknown"),
                    properties=emp_props,
                    group="Employee",
                    style=emp_style,
                )

            # 스킬 노드와 엣지 추가
            for skill_data in row["skills"]:
                skill_id = skill_data.get("skill_id")
                skill_props = skill_data.get("skill_props")
                rel_id = skill_data.get("rel_id")

                if skill_id and skill_props and rel_id:
                    if skill_id not in nodes_map:
                        skill_style = get_node_style(
                            "Skill", skill_props.get("name", "")
                        )
                        nodes_map[skill_id] = GraphNode(
                            id=skill_id,
                            label="Skill",
                            name=skill_props.get("name", "Unknown"),
                            properties=skill_props,
                            group="Skill",
                            style=skill_style,
                        )

                    if rel_id not in edges_map:
                        edges_map[rel_id] = GraphEdge(
                            id=rel_id,
                            source=emp_id,
                            target=skill_id,
                            label="HAS_SKILL",
                            properties={},
                        )

        nodes = list(nodes_map.values())
        edges = list(edges_map.values())

        return SubgraphResponse(
            success=True,
            center_node_id=str(request.community_id),
            nodes=nodes,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Community graph query failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"커뮤니티 그래프 조회 실패: {e}",
        ) from e


# ============================================
# 쿼리 결과 시각화
# ============================================


@router.post("/query-result", response_model=SubgraphResponse)
async def visualize_query_result(
    request: QueryResultVisualizationRequest,
    neo4j: Annotated[Neo4jRepository, Depends(get_neo4j_repository)],
) -> SubgraphResponse:
    """
    Cypher 쿼리 결과를 그래프 형식으로 반환

    노드와 관계를 반환하는 쿼리의 결과를 시각화 가능한 형식으로 변환합니다.
    쿼리에서 노드는 n, 관계는 r로 반환해야 합니다.

    ⚠️ 보안: READ-ONLY 쿼리만 허용됩니다.
    """
    logger.info(f"Query result visualization: {request.cypher_query[:50]}...")

    try:
        # 보안: READ-ONLY 쿼리만 허용
        try:
            validate_read_only_cypher(request.cypher_query)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

        results = await neo4j.execute_cypher(request.cypher_query, request.parameters)

        nodes_map: dict[str, GraphNode] = {}
        edges_map: dict[str, GraphEdge] = {}

        # 결과에서 노드와 관계 정보 추출 (dict 기반)
        for row in results:
            for key, value in row.items():
                if isinstance(value, dict):
                    # 노드 형식: {"id": "...", "labels": [...], "properties": {...}}
                    if "labels" in value and "properties" in value:
                        node_id = value.get("id", f"node_{len(nodes_map)}")
                        labels = value.get("labels", [])
                        props = value.get("properties", {})
                        if node_id not in nodes_map:
                            node_label = labels[0] if labels else "Node"
                            node_name = props.get("name", key)
                            node_style = get_node_style(node_label)

                            nodes_map[node_id] = GraphNode(
                                id=node_id,
                                label=node_label,
                                name=node_name,
                                properties=props,
                                group=node_label if labels else "default",
                                style=node_style,
                            )

        nodes = list(nodes_map.values())
        edges = list(edges_map.values())

        return SubgraphResponse(
            success=True,
            center_node_id="query_result",
            nodes=nodes,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
        )

    except Exception as e:
        logger.error(f"Query visualization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"쿼리 결과 시각화 실패: {e}",
        ) from e


# ============================================
# 스키마 시각화
# ============================================


@router.get("/schema", response_model=SchemaVisualizationResponse)
async def get_schema_visualization(
    neo4j: Annotated[Neo4jRepository, Depends(get_neo4j_repository)],
) -> SchemaVisualizationResponse:
    """
    데이터베이스 스키마를 그래프 형식으로 반환

    노드 타입과 관계 타입을 시각화할 수 있는 형식으로 반환합니다.
    """
    logger.info("Schema visualization request")

    try:
        schema = await neo4j.get_schema()

        # 노드 타입을 노드로 변환
        nodes = [
            GraphNode(
                id=f"label_{label}",
                label="NodeType",
                name=label,
                properties={},
                group="schema",
            )
            for label in schema.get("node_labels", [])
        ]

        # 관계 타입 조회
        rel_query = """
        CALL db.schema.visualization()
        YIELD nodes, relationships
        UNWIND relationships as rel
        RETURN DISTINCT
            labels(startNode(rel))[0] as from_label,
            type(rel) as rel_type,
            labels(endNode(rel))[0] as to_label
        """

        try:
            rel_results = await neo4j.execute_cypher(rel_query, {})
            edges = [
                GraphEdge(
                    id=f"rel_{row['from_label']}_{row['rel_type']}_{row['to_label']}",
                    source=f"label_{row['from_label']}",
                    target=f"label_{row['to_label']}",
                    label=row["rel_type"],
                    properties={},
                )
                for row in rel_results
            ]
        except Exception:
            # 스키마 시각화 프로시저가 없는 경우 빈 엣지 반환
            edges = []

        return SchemaVisualizationResponse(
            success=True,
            nodes=nodes,
            edges=edges,
        )

    except Exception as e:
        logger.error(f"Schema visualization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"스키마 시각화 실패: {e}",
        ) from e


# ============================================
# 쿼리 경로 시각화
# ============================================


@router.post("/query-path", response_model=QueryPathVisualizationResponse)
async def visualize_query_path(
    request: QueryPathVisualizationRequest,
    pipeline: Annotated[GraphRAGPipeline, Depends(get_graph_pipeline)],
    neo4j: Annotated[Neo4jRepository, Depends(get_neo4j_repository)],
) -> QueryPathVisualizationResponse:
    """
    자연어 쿼리의 실행 경로를 시각화

    질문을 분석하고, Multi-hop 쿼리 계획과 실행 결과를 그래프로 반환합니다.
    """
    logger.info(f"Query path visualization: {request.question[:50]}...")

    try:
        # 파이프라인 실행
        result = await pipeline.run(request.question)

        metadata = result.get("metadata", {})
        query_plan_data = metadata.get("query_plan", {})

        # 쿼리 계획 변환
        query_steps: list[QueryStep] = []
        hops = query_plan_data.get("hops", [])

        for hop in hops:
            query_steps.append(
                QueryStep(
                    step=hop.get("step", 0),
                    description=hop.get("description", ""),
                    node_label=hop.get("node_label"),
                    relationship=hop.get("relationship"),
                    result_count=0,
                    sample_results=[],
                )
            )

        # 쿼리 결과에서 그래프 데이터 추출
        nodes_map: dict[str, GraphNode] = {}
        edges_list: list[GraphEdge] = []

        # 엔티티 추출 (entities가 비어있으면 cypher_parameters에서 추출)
        entities = metadata.get("entities", {})
        if not entities or not any(entities.values()):
            # cypher_parameters에서 엔티티 값 추출
            cypher_params = metadata.get("cypher_parameters", {})
            for _key, value in cypher_params.items():
                if isinstance(value, str) and value:
                    entities.setdefault("extracted", []).append(value)
                elif isinstance(value, list):
                    for v in value:
                        if isinstance(v, str) and v:
                            entities.setdefault("extracted", []).append(v)
            logger.info(f"Extracted entities from cypher_parameters: {entities}")

        # Cypher 쿼리가 있으면 경로 시각화용 데이터 조회
        cypher_query = metadata.get("cypher_query")
        if cypher_query and result.get("success"):
            # 경로 추적을 위한 쿼리 실행 (간소화된 버전)
            try:
                path_query = _build_path_visualization_query(
                    entities,
                    query_plan_data,
                )
                logger.info(f"Path query: {path_query}")
                if path_query:
                    path_results = await neo4j.execute_cypher(
                        path_query["query"], path_query["params"]
                    )
                    logger.info(f"Path results count: {len(path_results)}")

                    # 시작점 이름들과 끝점 타입 결정
                    start_names = path_query["params"].get("start_names", [])

                    # 쿼리 계획의 마지막 hop에서 결과 타입 추출
                    end_label = None
                    if query_steps:
                        last_step = query_steps[-1]
                        end_label = last_step.node_label

                    # query_plan이 없으면 intent에서 결과 타입 추론
                    if not end_label:
                        intent = metadata.get("intent", "")
                        intent_to_end_label = {
                            "personnel_search": "Employee",
                            "skill_search": "Skill",
                            "team_structure": "Department",
                            "project_search": "Project",
                            "mentoring_network": "Employee",
                            "career_path": "Position",
                            "certification_search": "Certificate",
                            "expertise_analysis": "Skill",
                            "collaboration_network": "Employee",
                        }
                        end_label = intent_to_end_label.get(intent)

                    # Cypher 쿼리에서 RETURN 절 분석하여 결과 타입 추론
                    if not end_label and cypher_query:
                        cypher_upper = cypher_query.upper()
                        if "SKILL" in cypher_upper and "RETURN" in cypher_upper:
                            if "S.NAME" in cypher_upper or "SKILL.NAME" in cypher_upper:
                                end_label = "Skill"
                        elif "PROJECT" in cypher_upper and "P.NAME" in cypher_upper:
                            end_label = "Project"
                        elif "DEPARTMENT" in cypher_upper and "D.NAME" in cypher_upper:
                            end_label = "Department"

                    nodes_map, edges_list = _extract_path_graph(
                        path_results,
                        start_names=start_names,
                        end_label=end_label,
                    )
            except Exception as e:
                logger.warning(f"Path extraction failed: {e}")

        return QueryPathVisualizationResponse(
            success=result.get("success", False),
            question=request.question,
            intent=metadata.get("intent"),
            is_multi_hop=query_plan_data.get("is_multi_hop", False),
            query_plan=query_steps,
            nodes=list(nodes_map.values()),
            edges=edges_list,
            cypher_query=cypher_query,
            execution_path=metadata.get("execution_path", []),
            final_answer=result.get("response"),
        )

    except Exception as e:
        logger.error(f"Query path visualization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"쿼리 경로 시각화 실패: {e}",
        ) from e


def _build_path_visualization_query(
    entities: dict,
    query_plan: dict | None,
    cypher_query: str | None = None,
) -> dict | None:
    """경로 시각화를 위한 쿼리 생성 (실제 쿼리 패턴 기반)"""
    # 엔티티에서 시작점 찾기 (중복 제거)
    start_entities_set: set[str] = set()
    for _entity_type, values in entities.items():
        if values:
            for v in values[:3]:  # 각 타입에서 최대 3개
                start_entities_set.add(v)

    start_entities = list(start_entities_set)
    if not start_entities:
        return None

    # hop 수에 따라 탐색 깊이 결정
    hop_count = 2
    if query_plan and query_plan.get("is_multi_hop"):
        hop_count = min(query_plan.get("hop_count", 2), 3)

    # SIMILAR 관계 제외하고 의미있는 관계만 포함
    # (HAS_SKILL, BELONGS_TO, WORKS_ON, MENTORS, HAS_POSITION 등)
    meaningful_rels = [
        "HAS_SKILL",
        "BELONGS_TO",
        "WORKS_ON",
        "MENTORS",
        "MENTORED_BY",
        "HAS_POSITION",
        "MANAGES",
        "REPORTS_TO",
        "COLLABORATES_WITH",
        "OWNED_BY",
        "HAS_CERTIFICATE",
        "LOCATED_AT",
        "REQUIRES",
        "IS_A",
    ]
    rel_filter = " OR ".join([f"type(rel) = '{r}'" for r in meaningful_rels])

    # 노드와 관계를 모두 추출하는 쿼리 (SIMILAR 제외, 시각화용 제한)
    query = f"""
    MATCH (start)
    WHERE start.name IN $start_names
    CALL {{
        WITH start
        MATCH path = (start)-[*1..{hop_count}]-(connected)
        WHERE ALL(rel IN relationships(path) WHERE {rel_filter})
        RETURN path
        LIMIT 15
    }}
    WITH nodes(path) as pathNodes, relationships(path) as pathRels
    UNWIND pathNodes as n
    WITH DISTINCT n, pathRels
    UNWIND pathRels as r
    RETURN DISTINCT
        elementId(n) as node_id,
        labels(n) as labels,
        properties(n) as props,
        elementId(r) as rel_id,
        type(r) as rel_type,
        elementId(startNode(r)) as rel_source,
        elementId(endNode(r)) as rel_target
    LIMIT 80
    """

    return {"query": query, "params": {"start_names": start_entities}}


def _extract_path_graph(
    results: list[dict],
    start_names: list[str] | None = None,
    end_label: str | None = None,
) -> tuple[dict[str, GraphNode], list[GraphEdge]]:
    """쿼리 결과에서 그래프 데이터 추출 (노드 + 엣지, 시작점/끝점 표시)"""
    nodes_map: dict[str, GraphNode] = {}
    edges_map: dict[str, GraphEdge] = {}
    start_names_set = set(start_names) if start_names else set()

    for row in results:
        # 노드 추출
        node_id = row.get("node_id")
        labels = row.get("labels", [])
        props = sanitize_props(row.get("props", {}))
        node_name = props.get("name", "Unknown")
        node_label = labels[0] if labels else "Node"

        # 노드 역할 결정
        role = None
        if node_name in start_names_set:
            role = "start"
        elif end_label and node_label == end_label:
            role = "end"

        if node_id and node_id not in nodes_map:
            node_style = get_node_style(node_label)
            nodes_map[node_id] = GraphNode(
                id=node_id,
                label=node_label,
                name=node_name,
                properties=props,
                group=node_label if node_label else "default",
                role=role,
                style=node_style,
            )

        # 엣지 추출
        rel_id = row.get("rel_id")
        rel_type = row.get("rel_type")
        rel_source = row.get("rel_source")
        rel_target = row.get("rel_target")

        if rel_id and rel_id not in edges_map and rel_source and rel_target:
            edges_map[rel_id] = GraphEdge(
                id=rel_id,
                source=rel_source,
                target=rel_target,
                label=rel_type or "RELATED",
                properties={},
            )

    return nodes_map, list(edges_map.values())
