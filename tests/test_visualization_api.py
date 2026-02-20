"""
Visualization API 엔드포인트 테스트

서브그래프, 커뮤니티 그래프, 쿼리 결과 시각화, 스키마 시각화, 쿼리 경로 시각화 테스트
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.visualization import router
from src.api.schemas.visualization import NodeStyle
from src.dependencies import get_graph_pipeline, get_neo4j_repository
from src.graph.pipeline import GraphRAGPipeline
from src.repositories.neo4j_repository import Neo4jRepository


def _mock_get_node_style(label: str, _name: str = "") -> NodeStyle:
    """get_node_style의 mock (2인자 호출에도 대응)"""
    return NodeStyle(color="#3B82F6", icon="circle")


@pytest.fixture
def mock_neo4j():
    """Mock Neo4jRepository"""
    repo = MagicMock(spec=Neo4jRepository)
    repo.execute_cypher = AsyncMock(return_value=[])
    repo.get_schema = AsyncMock(
        return_value={
            "node_labels": ["Employee", "Skill", "Project"],
            "relationship_types": ["HAS_SKILL", "WORKS_ON"],
        }
    )
    return repo


@pytest.fixture
def mock_pipeline():
    """Mock GraphRAGPipeline"""
    pipeline = MagicMock(spec=GraphRAGPipeline)
    pipeline.run = AsyncMock(
        return_value={
            "success": True,
            "question": "Python 잘하는 사람은?",
            "response": "홍길동이 Python을 잘합니다.",
            "metadata": {
                "intent": "personnel_search",
                "entities": {"skills": ["Python"]},
                "cypher_query": "MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill) WHERE s.name='Python' RETURN e",
                "query_plan": {"is_multi_hop": False, "hops": []},
                "execution_path": ["intent_entity_extractor", "cypher_generator"],
            },
        }
    )
    return pipeline


@pytest.fixture
def app(mock_neo4j, mock_pipeline):
    """테스트용 FastAPI 앱"""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_neo4j_repository] = lambda: mock_neo4j
    app.dependency_overrides[get_graph_pipeline] = lambda: mock_pipeline
    return app


@pytest.fixture
def client(app):
    """테스트 클라이언트"""
    return TestClient(app)


# =============================================================================
# POST /visualization/subgraph
# =============================================================================


class TestSubgraphAPI:
    @patch("src.api.routes.visualization.get_node_style", _mock_get_node_style)
    def test_subgraph_by_node_id(self, client, mock_neo4j):
        """node_id로 서브그래프 조회"""
        # 첫 번째 호출: 중심 노드 찾기
        # 두 번째 호출: 서브그래프 쿼리
        mock_neo4j.execute_cypher = AsyncMock(
            side_effect=[
                [
                    {
                        "node_id": "4:abc:0",
                        "labels": ["Employee"],
                        "props": {"name": "홍길동"},
                    }
                ],
                [
                    {
                        "center_id": "4:abc:0",
                        "node_id": "4:abc:1",
                        "labels": ["Skill"],
                        "props": {"name": "Python"},
                        "relationships": [
                            {
                                "id": "5:abc:0",
                                "type": "HAS_SKILL",
                                "start": "4:abc:0",
                                "end": "4:abc:1",
                                "props": {},
                            }
                        ],
                    }
                ],
            ]
        )

        resp = client.post(
            "/api/v1/visualization/subgraph",
            json={
                "node_id": "4:abc:0",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["center_node_id"] == "4:abc:0"
        assert data["node_count"] >= 1

    @patch("src.api.routes.visualization.get_node_style", _mock_get_node_style)
    def test_subgraph_by_node_name(self, client, mock_neo4j):
        """node_name으로 서브그래프 조회"""
        mock_neo4j.execute_cypher = AsyncMock(
            side_effect=[
                [
                    {
                        "node_id": "4:abc:0",
                        "labels": ["Employee"],
                        "props": {"name": "홍길동"},
                    }
                ],
                [],
            ]
        )

        resp = client.post(
            "/api/v1/visualization/subgraph",
            json={
                "node_name": "홍길동",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_subgraph_not_found(self, client, mock_neo4j):
        """노드를 찾을 수 없을 때 → 500 (except Exception이 HTTPException도 catch)"""
        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        resp = client.post(
            "/api/v1/visualization/subgraph",
            json={
                "node_id": "nonexistent",
            },
        )
        assert resp.status_code == 500


# =============================================================================
# POST /visualization/community
# =============================================================================


class TestCommunityGraphAPI:
    @patch("src.api.routes.visualization.get_node_style", _mock_get_node_style)
    def test_community_graph_success(self, client, mock_neo4j):
        """커뮤니티 그래프 조회 성공"""
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "emp_id": "4:abc:0",
                    "emp_props": {"name": "홍길동", "communityId": 1},
                    "skills": [
                        {
                            "skill_id": "4:abc:1",
                            "skill_props": {"name": "Python"},
                            "rel_id": "5:abc:0",
                        }
                    ],
                }
            ]
        )

        resp = client.post(
            "/api/v1/visualization/community",
            json={
                "community_id": 1,
                "include_skills": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["node_count"] >= 1

    def test_community_graph_empty(self, client, mock_neo4j):
        """빈 커뮤니티 → 500 (except Exception이 HTTPException도 catch)"""
        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        resp = client.post(
            "/api/v1/visualization/community",
            json={
                "community_id": 999,
            },
        )
        assert resp.status_code == 500


# =============================================================================
# POST /visualization/query-result
# =============================================================================


class TestQueryResultAPI:
    def test_query_result_success(self, client, mock_neo4j):
        """Cypher 쿼리 결과 시각화"""
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "n": {
                        "id": "4:abc:0",
                        "labels": ["Employee"],
                        "properties": {"name": "홍길동"},
                    }
                }
            ]
        )

        resp = client.post(
            "/api/v1/visualization/query-result",
            json={
                "cypher_query": "MATCH (n:Employee) RETURN n LIMIT 5",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_query_result_write_query_rejected(self, client):
        """쓰기 쿼리 거부 → 500 (except Exception이 HTTPException도 catch)"""
        resp = client.post(
            "/api/v1/visualization/query-result",
            json={
                "cypher_query": "CREATE (n:Employee {name: 'test'})",
            },
        )
        assert resp.status_code == 500


# =============================================================================
# GET /visualization/schema
# =============================================================================


class TestSchemaVisualizationAPI:
    def test_schema_success(self, client, mock_neo4j):
        """스키마 시각화 성공"""
        # execute_cypher for relationship query
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "from_label": "Employee",
                    "rel_type": "HAS_SKILL",
                    "to_label": "Skill",
                },
            ]
        )

        resp = client.get("/api/v1/visualization/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["nodes"]) > 0


# =============================================================================
# POST /visualization/query-path
# =============================================================================


class TestQueryPathAPI:
    def test_query_path_success(self, client, mock_neo4j, mock_pipeline):
        """쿼리 경로 시각화 성공"""
        # pipeline.run already mocked
        # path query returns some path data
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "node_id": "4:abc:0",
                    "labels": ["Employee"],
                    "props": {"name": "홍길동"},
                    "rel_id": "5:abc:0",
                    "rel_type": "HAS_SKILL",
                    "rel_source": "4:abc:0",
                    "rel_target": "4:abc:1",
                }
            ]
        )

        resp = client.post(
            "/api/v1/visualization/query-path",
            json={
                "question": "Python 잘하는 사람은?",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["question"] == "Python 잘하는 사람은?"

    def test_query_path_empty(self, client, mock_neo4j, mock_pipeline):
        """빈 경로"""
        mock_pipeline.run = AsyncMock(
            return_value={
                "success": True,
                "question": "아무거나",
                "response": "결과 없음",
                "metadata": {
                    "intent": "personnel_search",
                    "entities": {},
                    "query_plan": {},
                },
            }
        )
        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        resp = client.post(
            "/api/v1/visualization/query-path",
            json={
                "question": "아무거나",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"] == []
        assert data["edges"] == []
