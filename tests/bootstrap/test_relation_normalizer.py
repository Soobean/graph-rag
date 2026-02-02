"""
RelationNormalizer 테스트

관계 정규화 기능을 테스트합니다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bootstrap.models import (
    NormalizationResult,
    RelationGroup,
    SchemaProposal,
    Triple,
)
from src.bootstrap.relation_normalizer import RelationNormalizer
from src.repositories.llm_repository import LLMRepository


@pytest.fixture
def mock_llm():
    """Mock LLM Repository"""
    llm = MagicMock(spec=LLMRepository)
    llm.generate_json = AsyncMock()
    llm.generate = AsyncMock()
    llm.close = AsyncMock()
    return llm


@pytest.fixture
def mock_prompt_manager():
    """Mock PromptManager"""
    pm = MagicMock()
    pm.load_prompt.return_value = {
        "system": "You are a normalization expert.",
        "user": "Group: {relations_with_frequency} {schema_hint}",
    }
    return pm


@pytest.fixture
def normalizer(mock_llm, mock_prompt_manager):
    """RelationNormalizer with mocks"""
    return RelationNormalizer(
        llm_repository=mock_llm,
        prompt_manager=mock_prompt_manager,
    )


@pytest.fixture
def sample_triples():
    """테스트용 트리플 목록"""
    return [
        Triple("홍길동", "참여했다", "AI 프로젝트", 0.9, "text1"),
        Triple("김영희", "작업했다", "ML 프로젝트", 0.85, "text2"),
        Triple("이철수", "참여했다", "Web 프로젝트", 0.8, "text3"),
        Triple("박지민", "담당했다", "Backend", 0.9, "text4"),
        Triple("최수진", "책임졌다", "Frontend", 0.85, "text5"),
    ]


class TestRelationNormalizer:
    """RelationNormalizer 테스트"""

    @pytest.mark.asyncio
    async def test_group_relations_success(
        self, normalizer, mock_llm, sample_triples
    ):
        """관계 그룹화 성공"""
        mock_llm.generate_json.return_value = {
            "groups": [
                {
                    "canonical_name": "WORKS_ON",
                    "variants": ["참여했다", "작업했다"],
                    "description": "프로젝트 참여 관계",
                },
                {
                    "canonical_name": "MANAGES",
                    "variants": ["담당했다", "책임졌다"],
                    "description": "관리/담당 관계",
                },
            ],
            "unmapped": [],
        }

        result = await normalizer.group_relations(triples=sample_triples)

        assert isinstance(result, NormalizationResult)
        assert len(result.groups) == 2
        assert "참여했다" in result.mapping
        assert result.mapping["참여했다"] == "WORKS_ON"

    @pytest.mark.asyncio
    async def test_group_relations_empty_triples(self, normalizer):
        """빈 트리플 목록"""
        result = await normalizer.group_relations(triples=[])
        assert isinstance(result, NormalizationResult)
        assert len(result.groups) == 0

    @pytest.mark.asyncio
    async def test_group_relations_with_schema_hint(
        self, normalizer, mock_llm, sample_triples
    ):
        """스키마 힌트와 함께 그룹화"""
        mock_llm.generate_json.return_value = {
            "groups": [
                {
                    "canonical_name": "WORKS_ON",
                    "variants": ["참여했다", "작업했다"],
                    "description": "",
                }
            ],
            "unmapped": ["담당했다", "책임졌다"],
        }

        schema = SchemaProposal(
            node_labels=["Employee", "Project"],
            relationship_types=["WORKS_ON"],
            properties={},
        )

        result = await normalizer.group_relations(
            triples=sample_triples,
            schema_hint=schema,
        )

        assert len(result.unmapped_relations) > 0

    @pytest.mark.asyncio
    async def test_group_relations_min_frequency(
        self, normalizer, mock_llm
    ):
        """최소 빈도 필터링"""
        # 같은 관계가 2번만 등장
        triples = [
            Triple("A", "rare_relation", "B", 0.9, ""),
            Triple("C", "common_relation", "D", 0.9, ""),
            Triple("E", "common_relation", "F", 0.9, ""),
            Triple("G", "common_relation", "H", 0.9, ""),
        ]

        mock_llm.generate_json.return_value = {
            "groups": [
                {
                    "canonical_name": "COMMON",
                    "variants": ["common_relation"],
                    "description": "",
                }
            ],
            "unmapped": [],
        }

        result = await normalizer.group_relations(
            triples=triples,
            min_frequency=2,
        )

        # rare_relation은 1번만 등장하므로 제외
        assert "rare_relation" not in result.mapping

    def test_normalize_triples(self, normalizer, sample_triples):
        """트리플 정규화"""
        norm_result = NormalizationResult(
            groups=[
                RelationGroup("WORKS_ON", ["참여했다", "작업했다"], 3),
                RelationGroup("MANAGES", ["담당했다", "책임졌다"], 2),
            ],
            mapping={
                "참여했다": "WORKS_ON",
                "작업했다": "WORKS_ON",
                "담당했다": "MANAGES",
                "책임졌다": "MANAGES",
            },
        )

        normalized = normalizer.normalize_triples(sample_triples, norm_result)

        assert len(normalized) == 5
        # 정규화된 관계 확인
        relations = [t.relation for t in normalized]
        assert "WORKS_ON" in relations
        assert "MANAGES" in relations
        # 원본 관계는 없어야 함
        assert "참여했다" not in relations

    def test_merge_groups_with_manual_mappings(self, normalizer):
        """수동 매핑으로 그룹 병합"""
        groups = [
            RelationGroup("GROUP_A", ["a1", "a2"], 2),
            RelationGroup("GROUP_B", ["b1"], 1),
        ]

        manual_mappings = {
            "a1": "GROUP_B",  # a1을 GROUP_B로 이동
        }

        result = normalizer.merge_groups(groups, manual_mappings)

        # GROUP_B에 a1이 추가되어야 함
        group_b = next(g for g in result if g.canonical_name == "GROUP_B")
        assert "a1" in group_b.variants
        assert "b1" in group_b.variants

    def test_merge_groups_creates_new_group(self, normalizer):
        """수동 매핑으로 새 그룹 생성"""
        groups = [
            RelationGroup("EXISTING", ["e1"], 1),
        ]

        manual_mappings = {
            "new_variant": "NEW_GROUP",
        }

        result = normalizer.merge_groups(groups, manual_mappings)

        # 새 그룹이 생성되어야 함
        group_names = [g.canonical_name for g in result]
        assert "NEW_GROUP" in group_names

    def test_merge_groups_empty_mappings(self, normalizer):
        """빈 매핑은 그대로 반환"""
        groups = [RelationGroup("TEST", ["t1"], 1)]

        result = normalizer.merge_groups(groups, {})
        assert result == groups

    @pytest.mark.asyncio
    async def test_suggest_canonical_name(self, normalizer, mock_llm):
        """대표 이름 제안"""
        mock_llm.generate.return_value = "WORKS_ON"

        result = await normalizer.suggest_canonical_name(
            variants=["참여했다", "작업했다", "개발했다"]
        )

        assert result == "WORKS_ON"
        mock_llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_suggest_canonical_name_empty_raises_error(self, normalizer):
        """빈 변형 목록은 에러"""
        with pytest.raises(ValueError, match="(?i)at least one"):
            await normalizer.suggest_canonical_name(variants=[])

    def test_format_relations_with_frequency(self, normalizer):
        """관계 빈도 포맷팅"""
        relation_counts = {
            "참여했다": 10,
            "담당했다": 5,
            "알고있다": 2,
        }

        result = normalizer._format_relations_with_frequency(relation_counts)

        assert "참여했다" in result
        assert "10회" in result
        # 빈도순 정렬 확인 (참여했다가 먼저)
        assert result.index("참여했다") < result.index("담당했다")

    def test_format_schema_hint_none(self, normalizer):
        """스키마 없을 때"""
        result = normalizer._format_schema_hint(None)
        assert "힌트 없음" in result

    def test_format_schema_hint_with_schema(self, normalizer):
        """스키마 있을 때"""
        schema = SchemaProposal(
            node_labels=[],
            relationship_types=["WORKS_ON", "HAS_SKILL"],
            properties={},
        )

        result = normalizer._format_schema_hint(schema)
        assert "WORKS_ON" in result
        assert "HAS_SKILL" in result

    def test_parse_grouping_response(self, normalizer, sample_triples):
        """그룹화 응답 파싱"""
        from collections import Counter

        relation_counts = Counter(t.relation for t in sample_triples)

        response = {
            "groups": [
                {
                    "canonical_name": "WORKS_ON",
                    "variants": ["참여했다", "작업했다"],
                    "description": "Project participation",
                }
            ],
            "unmapped": ["담당했다"],
        }

        result = normalizer._parse_grouping_response(
            response=response,
            triples=sample_triples,
            relation_counts=relation_counts,
        )

        assert len(result.groups) == 1
        assert result.groups[0].canonical_name == "WORKS_ON"
        assert "담당했다" in result.unmapped_relations
        assert result.mapping["참여했다"] == "WORKS_ON"
