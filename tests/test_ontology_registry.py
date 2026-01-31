"""
OntologyRegistry 테스트

온톨로지 로더 생명주기 관리 및 캐시 새로고침 기능을 테스트합니다.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.ontology.hybrid_loader import HybridOntologyLoader
from src.domain.ontology.loader import OntologyLoader, get_ontology_loader
from src.domain.ontology.registry import OntologyRegistry


class TestOntologyRegistryInit:
    """OntologyRegistry 초기화 테스트"""

    def test_init_yaml_mode_default(self):
        """기본 모드는 YAML"""
        registry = OntologyRegistry()

        assert registry.mode == "yaml"
        assert isinstance(registry.get_loader(), OntologyLoader)

    def test_init_yaml_mode_explicit(self):
        """명시적 YAML 모드"""
        registry = OntologyRegistry(mode="yaml")

        assert registry.mode == "yaml"
        assert isinstance(registry.get_loader(), OntologyLoader)

    def test_init_neo4j_mode_without_client_raises(self):
        """neo4j 모드에서 클라이언트 없으면 에러"""
        with pytest.raises(ValueError, match="neo4j_client is required"):
            OntologyRegistry(mode="neo4j")

    def test_init_hybrid_mode_without_client_raises(self):
        """hybrid 모드에서 클라이언트 없으면 에러"""
        with pytest.raises(ValueError, match="neo4j_client is required"):
            OntologyRegistry(mode="hybrid")

    def test_init_neo4j_mode_with_client(self):
        """neo4j 모드 정상 초기화"""
        mock_client = MagicMock()

        registry = OntologyRegistry(neo4j_client=mock_client, mode="neo4j")

        assert registry.mode == "neo4j"
        assert isinstance(registry.get_loader(), HybridOntologyLoader)

    def test_init_hybrid_mode_with_client(self):
        """hybrid 모드 정상 초기화"""
        mock_client = MagicMock()

        registry = OntologyRegistry(neo4j_client=mock_client, mode="hybrid")

        assert registry.mode == "hybrid"
        assert isinstance(registry.get_loader(), HybridOntologyLoader)

    def test_init_mode_from_settings(self):
        """settings에서 모드 가져오기"""
        mock_settings = MagicMock()
        mock_settings.ontology_mode = "yaml"

        registry = OntologyRegistry(settings=mock_settings)

        assert registry.mode == "yaml"

    def test_init_explicit_mode_overrides_settings(self):
        """명시적 모드가 settings보다 우선"""
        mock_settings = MagicMock()
        mock_settings.ontology_mode = "neo4j"

        registry = OntologyRegistry(settings=mock_settings, mode="yaml")

        assert registry.mode == "yaml"


class TestOntologyRegistryYamlRefresh:
    """YAML 모드 캐시 새로고침 테스트"""

    @pytest.fixture
    def yaml_registry(self):
        """YAML 모드 레지스트리"""
        return OntologyRegistry(mode="yaml")

    @pytest.mark.asyncio
    async def test_refresh_yaml_mode_clears_lru_cache(self, yaml_registry):
        """YAML 모드 refresh가 lru_cache를 클리어"""
        # 캐시에 인스턴스 로드
        _ = get_ontology_loader()
        assert get_ontology_loader.cache_info().currsize == 1

        # refresh 호출
        result = await yaml_registry.refresh()

        assert result is True
        # lru_cache가 클리어되었지만, 새 인스턴스가 생성됨
        assert get_ontology_loader.cache_info().currsize == 1

    @pytest.mark.asyncio
    async def test_refresh_yaml_mode_replaces_loader_instance(self, yaml_registry):
        """YAML 모드 refresh가 새 로더 인스턴스로 교체"""
        old_loader = yaml_registry.get_loader()

        # 내부 캐시 로드
        _ = old_loader.load_schema()
        _ = old_loader.load_synonyms()
        assert old_loader._schema is not None
        assert old_loader._synonyms is not None

        # refresh 호출
        result = await yaml_registry.refresh()

        assert result is True

        # 새 로더 인스턴스로 교체됨 (기존 인스턴스와 다름)
        new_loader = yaml_registry.get_loader()
        assert new_loader is not old_loader

        # 새 로더 인스턴스는 캐시가 비어있음
        assert new_loader._schema is None
        assert new_loader._synonyms is None


class TestOntologyRegistryHybridRefresh:
    """Hybrid 모드 캐시 새로고침 테스트"""

    @pytest.fixture
    def hybrid_registry(self):
        """Hybrid 모드 레지스트리"""
        mock_client = MagicMock()
        return OntologyRegistry(neo4j_client=mock_client, mode="hybrid")

    @pytest.mark.asyncio
    async def test_refresh_hybrid_mode_clears_yaml_cache(self, hybrid_registry):
        """Hybrid 모드 refresh가 YAML 캐시를 클리어"""
        loader = hybrid_registry.get_loader()
        yaml_loader = loader._yaml_loader

        # YAML 캐시 로드
        _ = yaml_loader.load_schema()
        _ = yaml_loader.load_synonyms()
        assert yaml_loader._schema is not None

        # refresh 호출
        result = await hybrid_registry.refresh()

        assert result is True
        assert yaml_loader._schema is None
        assert yaml_loader._synonyms is None

    @pytest.mark.asyncio
    async def test_refresh_hybrid_mode_clears_neo4j_cache(self, hybrid_registry):
        """Hybrid 모드 refresh가 Neo4j 캐시를 클리어 (있는 경우)"""
        loader = hybrid_registry.get_loader()
        neo4j_loader = loader._neo4j_loader

        # clear_cache 메서드가 있다면 호출되어야 함
        neo4j_loader.clear_cache = AsyncMock()

        result = await hybrid_registry.refresh()

        assert result is True
        neo4j_loader.clear_cache.assert_called_once()


class TestOntologyRegistryThreadSafety:
    """스레드 안전성 테스트"""

    @pytest.mark.asyncio
    async def test_concurrent_refresh_is_serialized(self):
        """동시 refresh 호출이 직렬화됨"""
        registry = OntologyRegistry(mode="yaml")

        # refresh 호출 추적
        call_order = []
        original_do_refresh = registry._do_refresh

        async def tracked_refresh():
            call_order.append("start")
            await asyncio.sleep(0.01)  # 작은 지연
            result = await original_do_refresh()
            call_order.append("end")
            return result

        registry._do_refresh = tracked_refresh

        # 동시에 3개의 refresh 호출
        results = await asyncio.gather(
            registry.refresh(),
            registry.refresh(),
            registry.refresh(),
        )

        # 모두 성공
        assert all(results)
        # 직렬화되어 순차 실행됨 (start-end가 교차하지 않음)
        assert call_order == ["start", "end", "start", "end", "start", "end"]


class TestOntologyRegistryErrorHandling:
    """에러 처리 테스트"""

    @pytest.mark.asyncio
    async def test_refresh_exception_returns_false(self):
        """refresh 중 예외 발생 시 False 반환"""
        registry = OntologyRegistry(mode="yaml")

        # 예외를 발생시키도록 패치
        with patch.object(
            registry, "_do_refresh", side_effect=Exception("Test error")
        ):
            result = await registry.refresh()

        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_does_not_propagate_exception(self):
        """refresh 예외가 외부로 전파되지 않음"""
        registry = OntologyRegistry(mode="yaml")

        with patch.object(
            registry, "_do_refresh", side_effect=RuntimeError("Critical error")
        ):
            # 예외가 전파되지 않아야 함
            result = await registry.refresh()
            assert result is False


class TestOntologyRegistryIntegration:
    """통합 테스트"""

    @pytest.mark.asyncio
    async def test_get_loader_returns_same_instance(self):
        """get_loader가 동일 인스턴스 반환"""
        registry = OntologyRegistry(mode="yaml")

        loader1 = registry.get_loader()
        loader2 = registry.get_loader()

        assert loader1 is loader2

    @pytest.mark.asyncio
    async def test_refresh_updates_loader_reference(self):
        """YAML 모드에서 refresh 후 새 로더 인스턴스"""
        registry = OntologyRegistry(mode="yaml")

        loader_before = registry.get_loader()
        await registry.refresh()
        loader_after = registry.get_loader()

        # YAML 모드에서는 새 싱글톤 인스턴스로 교체됨
        # (lru_cache 클리어 후 새 인스턴스 생성)
        assert loader_before is not loader_after

    @pytest.mark.asyncio
    async def test_loader_still_works_after_refresh(self):
        """refresh 후에도 로더가 정상 동작"""
        registry = OntologyRegistry(mode="yaml")

        await registry.refresh()
        loader = registry.get_loader()

        # 기본 동작 확인
        canonical = loader.get_canonical("Python", "skills")
        assert canonical == "Python"
