"""
Neo4jOntologyLoader 및 HybridOntologyLoader 테스트

유닛 테스트 (Mock 사용):
- Neo4jOntologyLoader 메서드 동작 검증
- HybridOntologyLoader 모드별 동작 검증

통합 테스트 (실제 Neo4j 필요):
- @pytest.mark.integration 마커 사용
- 실행: pytest -m integration
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.ontology.loader import ExpansionConfig


# ============================================================================
# Neo4jOntologyLoader 유닛 테스트 (Mock)
# ============================================================================


class TestNeo4jOntologyLoader:
    """Neo4jOntologyLoader 유닛 테스트"""

    @pytest.fixture
    def mock_client(self):
        """Mock Neo4jClient"""
        client = MagicMock()
        client.execute_query = AsyncMock()
        return client

    @pytest.fixture
    def loader(self, mock_client):
        """Neo4jOntologyLoader with mocked client"""
        from src.domain.ontology.neo4j_loader import Neo4jOntologyLoader
        return Neo4jOntologyLoader(mock_client)

    # -------------------------------------------------------------------------
    # get_canonical 테스트
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_canonical_found(self, loader, mock_client):
        """canonical 이름 찾기 성공"""
        mock_client.execute_query.return_value = [{"canonical_name": "Python"}]

        result = await loader.get_canonical("파이썬", "skills")

        assert result == "Python"
        mock_client.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_canonical_not_found(self, loader, mock_client):
        """canonical 이름 못찾음 - 원본 반환"""
        mock_client.execute_query.return_value = [{"canonical_name": None}]

        result = await loader.get_canonical("UnknownSkill", "skills")

        assert result == "UnknownSkill"

    @pytest.mark.asyncio
    async def test_get_canonical_non_skills_category(self, loader, mock_client):
        """skills 외 카테고리는 원본 반환"""
        result = await loader.get_canonical("test", "positions")

        assert result == "test"
        mock_client.execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_canonical_query_error(self, loader, mock_client):
        """쿼리 에러 시 원본 반환"""
        mock_client.execute_query.side_effect = Exception("DB Error")

        result = await loader.get_canonical("파이썬", "skills")

        assert result == "파이썬"

    # -------------------------------------------------------------------------
    # get_synonyms 테스트
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_synonyms_found(self, loader, mock_client):
        """동의어 목록 조회 성공"""
        mock_client.execute_query.return_value = [
            {"canonical": "Python", "synonyms": ["파이썬", "Python3", "Py"]}
        ]

        result = await loader.get_synonyms("파이썬", "skills")

        assert "Python" in result
        assert "파이썬" in result
        assert "Python3" in result

    @pytest.mark.asyncio
    async def test_get_synonyms_not_found(self, loader, mock_client):
        """동의어 없음 - 원본만 반환"""
        mock_client.execute_query.side_effect = [
            [{"canonical_name": None}],  # get_canonical
            [],  # get_synonyms
        ]

        result = await loader.get_synonyms("UnknownSkill", "skills")

        assert result == ["UnknownSkill"]

    # -------------------------------------------------------------------------
    # get_children 테스트
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_children_found(self, loader, mock_client):
        """하위 개념 조회 성공"""
        mock_client.execute_query.return_value = [
            {"children": ["Python", "Java", "Node.js", "Go"]}
        ]

        result = await loader.get_children("Backend", "skills")

        assert "Python" in result
        assert "Java" in result
        assert "Node.js" in result

    @pytest.mark.asyncio
    async def test_get_children_not_found(self, loader, mock_client):
        """하위 개념 없음"""
        mock_client.execute_query.return_value = [{"children": None}]

        result = await loader.get_children("UnknownCategory", "skills")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_children_non_skills_category(self, loader, mock_client):
        """skills 외 카테고리는 빈 리스트"""
        result = await loader.get_children("Senior", "positions")

        assert result == []
        mock_client.execute_query.assert_not_called()

    # -------------------------------------------------------------------------
    # expand_concept 테스트
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_expand_concept_success(self, loader, mock_client):
        """개념 확장 성공"""
        # expand_concept은 내부적으로 여러 쿼리를 호출함:
        # 1. get_canonical -> canonical_name 반환
        # 2. get_synonyms_with_weights -> canonical, synonyms 반환
        # 3. get_children -> children 반환
        mock_client.execute_query.side_effect = [
            # get_canonical 응답
            [{"canonical_name": "Python"}],
            # get_synonyms_with_weights 응답
            [{"canonical": "Python", "synonyms": [{"name": "파이썬", "weight": 1.0}, {"name": "Python3", "weight": 0.8}]}],
            # get_children 응답
            [{"children": ["Django", "FastAPI"]}],
        ]

        result = await loader.expand_concept("파이썬", "skills")

        assert "파이썬" in result
        assert "Python" in result
        assert len(result) <= 15  # default max_total

    @pytest.mark.asyncio
    async def test_expand_concept_with_config(self, loader, mock_client):
        """config 적용 확장"""
        mock_client.execute_query.return_value = [
            {"expanded": ["파이썬", "Python", "Python3"]}
        ]

        config = ExpansionConfig(max_synonyms=2, max_children=0, max_total=3)
        result = await loader.expand_concept("파이썬", "skills", config)

        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_expand_concept_query_error(self, loader, mock_client):
        """쿼리 에러 시 원본만 반환"""
        mock_client.execute_query.side_effect = Exception("DB Error")

        result = await loader.expand_concept("파이썬", "skills")

        assert result == ["파이썬"]

    # -------------------------------------------------------------------------
    # get_all_skills 테스트
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_all_skills(self, loader, mock_client):
        """모든 canonical 스킬 조회"""
        mock_client.execute_query.return_value = [
            {"skills": ["Python", "Java", "React", "Vue"]}
        ]

        result = await loader.get_all_skills()

        assert "Python" in result
        assert "Java" in result

    # -------------------------------------------------------------------------
    # health_check 테스트
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, loader, mock_client):
        """정상 상태 확인"""
        mock_client.execute_query.return_value = [
            {"concept_stats": [
                {"type": "skill", "count": 32},
                {"type": "category", "count": 3},
            ]}
        ]

        result = await loader.health_check()

        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_error(self, loader, mock_client):
        """에러 상태"""
        mock_client.execute_query.side_effect = Exception("Connection failed")

        result = await loader.health_check()

        assert result["status"] == "unhealthy"
        assert "error" in result


# ============================================================================
# HybridOntologyLoader 유닛 테스트
# ============================================================================


class TestHybridOntologyLoader:
    """HybridOntologyLoader 테스트"""

    @pytest.fixture
    def mock_neo4j_client(self):
        """Mock Neo4jClient"""
        client = MagicMock()
        client.execute_query = AsyncMock()
        return client

    # -------------------------------------------------------------------------
    # 초기화 테스트
    # -------------------------------------------------------------------------

    def test_init_yaml_mode(self):
        """YAML 모드 초기화"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        loader = HybridOntologyLoader(mode="yaml")

        assert loader.mode == "yaml"
        assert loader._yaml_loader is not None
        assert loader._neo4j_loader is None

    def test_init_neo4j_mode(self, mock_neo4j_client):
        """Neo4j 모드 초기화"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        loader = HybridOntologyLoader(
            neo4j_client=mock_neo4j_client,
            mode="neo4j"
        )

        assert loader.mode == "neo4j"
        assert loader._yaml_loader is None
        assert loader._neo4j_loader is not None

    def test_init_hybrid_mode(self, mock_neo4j_client):
        """하이브리드 모드 초기화"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        loader = HybridOntologyLoader(
            neo4j_client=mock_neo4j_client,
            mode="hybrid"
        )

        assert loader.mode == "hybrid"
        assert loader._yaml_loader is not None
        assert loader._neo4j_loader is not None

    def test_init_neo4j_mode_without_client(self):
        """Neo4j 모드인데 client 없으면 에러"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        with pytest.raises(ValueError, match="neo4j_client is required"):
            HybridOntologyLoader(mode="neo4j")

    def test_init_hybrid_mode_without_client(self):
        """하이브리드 모드인데 client 없으면 에러"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        with pytest.raises(ValueError, match="neo4j_client is required"):
            HybridOntologyLoader(mode="hybrid")

    # -------------------------------------------------------------------------
    # YAML 모드 테스트
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_yaml_mode_get_canonical(self):
        """YAML 모드 - get_canonical"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        loader = HybridOntologyLoader(mode="yaml")
        result = await loader.get_canonical("파이썬", "skills")

        assert result == "Python"

    @pytest.mark.asyncio
    async def test_yaml_mode_get_synonyms(self):
        """YAML 모드 - get_synonyms"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        loader = HybridOntologyLoader(mode="yaml")
        result = await loader.get_synonyms("파이썬", "skills")

        assert "Python" in result
        assert "파이썬" in result

    @pytest.mark.asyncio
    async def test_yaml_mode_get_children(self):
        """YAML 모드 - get_children"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        loader = HybridOntologyLoader(mode="yaml")
        result = await loader.get_children("Backend", "skills")

        assert "Python" in result
        assert "Java" in result

    @pytest.mark.asyncio
    async def test_yaml_mode_expand_concept(self):
        """YAML 모드 - expand_concept"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        loader = HybridOntologyLoader(mode="yaml")
        result = await loader.expand_concept("파이썬", "skills")

        assert "Python" in result
        assert "파이썬" in result

    # -------------------------------------------------------------------------
    # Neo4j 모드 테스트 (Mock)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_neo4j_mode_get_canonical(self, mock_neo4j_client):
        """Neo4j 모드 - get_canonical"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        mock_neo4j_client.execute_query.return_value = [{"canonical_name": "Python"}]

        loader = HybridOntologyLoader(
            neo4j_client=mock_neo4j_client,
            mode="neo4j"
        )
        result = await loader.get_canonical("파이썬", "skills")

        assert result == "Python"
        mock_neo4j_client.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_neo4j_mode_expand_concept(self, mock_neo4j_client):
        """Neo4j 모드 - expand_concept"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        # expand_concept은 내부적으로 여러 쿼리를 호출함
        mock_neo4j_client.execute_query.side_effect = [
            # get_canonical 응답
            [{"canonical_name": "Python"}],
            # get_synonyms_with_weights 응답
            [{"canonical": "Python", "synonyms": [{"name": "파이썬", "weight": 1.0}]}],
            # get_children 응답
            [{"children": []}],
        ]

        loader = HybridOntologyLoader(
            neo4j_client=mock_neo4j_client,
            mode="neo4j"
        )
        result = await loader.expand_concept("파이썬", "skills")

        assert "Python" in result

    # -------------------------------------------------------------------------
    # 하이브리드 모드 테스트 (Fallback)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_hybrid_mode_fallback_on_error(self, mock_neo4j_client):
        """하이브리드 모드 - Neo4j 에러 시 YAML로 폴백"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        mock_neo4j_client.execute_query.side_effect = Exception("Connection failed")

        loader = HybridOntologyLoader(
            neo4j_client=mock_neo4j_client,
            mode="hybrid"
        )
        result = await loader.get_canonical("파이썬", "skills")

        # YAML 폴백으로 정상 결과
        assert result == "Python"

    @pytest.mark.asyncio
    async def test_hybrid_mode_fallback_on_empty(self, mock_neo4j_client):
        """하이브리드 모드 - Neo4j 결과 없으면 YAML로 폴백"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        # Neo4j에서 못찾음 (term 그대로 반환)
        mock_neo4j_client.execute_query.return_value = [{"canonical_name": None}]

        loader = HybridOntologyLoader(
            neo4j_client=mock_neo4j_client,
            mode="hybrid"
        )
        result = await loader.get_canonical("파이썬", "skills")

        # YAML 폴백으로 정상 결과
        assert result == "Python"

    # -------------------------------------------------------------------------
    # health_check 테스트
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_health_check_yaml_mode(self):
        """YAML 모드 health_check"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        loader = HybridOntologyLoader(mode="yaml")
        result = await loader.health_check()

        assert result["mode"] == "yaml"
        assert result["yaml_available"] is True
        assert result["neo4j_available"] is False

    @pytest.mark.asyncio
    async def test_health_check_hybrid_mode(self, mock_neo4j_client):
        """하이브리드 모드 health_check"""
        from src.domain.ontology.hybrid_loader import HybridOntologyLoader

        mock_neo4j_client.execute_query.return_value = [
            {"concept_stats": [{"type": "skill", "count": 32}]}
        ]

        loader = HybridOntologyLoader(
            neo4j_client=mock_neo4j_client,
            mode="hybrid"
        )
        result = await loader.health_check()

        assert result["mode"] == "hybrid"
        assert result["yaml_available"] is True
        assert result["neo4j_available"] is True


# ============================================================================
# 통합 테스트 (실제 Neo4j 필요)
# ============================================================================


@pytest.mark.integration
class TestNeo4jOntologyLoaderIntegration:
    """
    Neo4j 통합 테스트

    실행 방법:
        pytest tests/test_neo4j_ontology_loader.py -m integration

    사전 조건:
        1. Neo4j 실행 중 (bolt://localhost:7687)
        2. python scripts/migrate_ontology.py 실행 완료
    """

    @pytest.fixture
    async def neo4j_client(self):
        """실제 Neo4j 클라이언트"""
        from src.infrastructure.neo4j_client import Neo4jClient

        client = Neo4jClient(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password123",
        )
        try:
            await client.connect()
            yield client
        except Exception:
            pytest.skip("Neo4j not available")
        finally:
            await client.close()

    @pytest.fixture
    async def loader(self, neo4j_client):
        """실제 Neo4jOntologyLoader"""
        from src.domain.ontology.neo4j_loader import Neo4jOntologyLoader
        return Neo4jOntologyLoader(neo4j_client)

    @pytest.mark.asyncio
    async def test_get_canonical_integration(self, loader):
        """실제 DB에서 canonical 조회"""
        result = await loader.get_canonical("파이썬", "skills")
        assert result == "Python"

    @pytest.mark.asyncio
    async def test_get_synonyms_integration(self, loader):
        """실제 DB에서 동의어 조회"""
        result = await loader.get_synonyms("Python", "skills")
        assert "Python" in result
        assert len(result) > 1  # 동의어가 있어야 함

    @pytest.mark.asyncio
    async def test_get_children_integration(self, loader):
        """실제 DB에서 하위 개념 조회"""
        result = await loader.get_children("Backend", "skills")
        assert "Python" in result
        assert "Java" in result

    @pytest.mark.asyncio
    async def test_expand_concept_integration(self, loader):
        """실제 DB에서 개념 확장"""
        result = await loader.expand_concept("파이썬", "skills")
        assert "Python" in result
        assert "파이썬" in result

    @pytest.mark.asyncio
    async def test_yaml_neo4j_consistency(self, loader):
        """YAML과 Neo4j 결과 일치 확인"""
        from src.domain.ontology.loader import OntologyLoader

        yaml_loader = OntologyLoader()

        # 동의어 비교
        yaml_synonyms = set(yaml_loader.get_synonyms("Python", "skills"))
        neo4j_synonyms = set(await loader.get_synonyms("Python", "skills"))

        # Neo4j가 YAML의 상위 집합이어야 함 (동일하거나 더 많아야 함)
        assert yaml_synonyms.issubset(neo4j_synonyms) or yaml_synonyms == neo4j_synonyms, \
            f"YAML: {yaml_synonyms}, Neo4j: {neo4j_synonyms}"
