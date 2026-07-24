"""
Cypher 실행 전 검증 단위 테스트 (속성 환각 감지)

실행 방법:
    pytest tests/domain/test_cypher_validations.py -v
"""

from src.domain.cypher import find_unknown_properties

SCHEMA = {
    "nodes": [
        {
            "label": "Employee",
            "properties": [{"name": "name"}, {"name": "hourly_rate"}],
        },
        {"label": "Skill", "properties": [{"name": "name"}, {"name": "category"}]},
    ],
    "relationships": [
        {
            "type": "REQUIRES",
            "properties": [
                {"name": "required_proficiency"},
                {"name": "max_hourly_rate"},
            ],
        },
    ],
}


class TestFindUnknownProperties:
    def test_known_properties_pass(self):
        cypher = (
            "MATCH (e:Employee)-[r:REQUIRES]->(s:Skill) "
            "WHERE toLower(s.name) = toLower($x) AND r.required_proficiency = '고급' "
            "RETURN e.name, e.hourly_rate"
        )
        assert find_unknown_properties(cypher, SCHEMA) == []

    def test_hallucinated_property_flagged(self):
        """s04 실증 사례: 존재하지 않는 importance 필터"""
        cypher = "MATCH (p)-[req:REQUIRES]->(s) WHERE req.importance = '필수' RETURN s"
        assert find_unknown_properties(cypher, SCHEMA) == ["importance"]

    def test_quoted_strings_ignored(self):
        """문자열 리터럴 내부의 점 표기는 속성 참조가 아님"""
        cypher = "MATCH (s:Skill) WHERE s.name = 'ML.NET' RETURN s.category"
        assert find_unknown_properties(cypher, SCHEMA) == []

    def test_schema_without_property_info_skips_validation(self):
        """labels만 있는 축약 스키마 → 검증 불가 → 빈 목록 (false positive 방지)"""
        cypher = "MATCH (e) WHERE e.anything = 1 RETURN e"
        assert find_unknown_properties(cypher, {"node_labels": ["Employee"]}) == []

    def test_duplicates_reported_once(self):
        cypher = "WHERE r.importance = 'a' AND r.importance = 'b'"
        assert find_unknown_properties(cypher, SCHEMA) == ["importance"]

    def test_map_style_access_flagged(self):
        """q16 실증 사례: 맵 속성을 패턴에 사용한 무효 접근도 감지됨"""
        cypher = "OPTIONAL MATCH (stat.mentor)-[:HAS_POSITION]->(p)"
        assert "mentor" in find_unknown_properties(cypher, SCHEMA)
