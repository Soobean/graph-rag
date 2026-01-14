from typing import Any

from pydantic import BaseModel, Field


class Style(BaseModel):
    """스타일 정보"""

    color: str = Field(..., description="HEX 색상 코드")
    icon: str = Field(..., description="아이콘 이름 (Lucide/FontAwesome)")


class ConceptBase(BaseModel):
    """기본 개념 정보"""

    name: str = Field(..., description="개념 이름")
    description: str | None = Field(default=None, description="설명")
    style: Style | None = Field(default=None, description="스타일 메타데이터")


class SkillCategory(ConceptBase):
    """스킬 카테고리"""

    skills: list[str] = Field(default_factory=list, description="포함된 스킬 목록")
    subcategories: list["SkillCategory"] = Field(
        default_factory=list, description="하위 카테고리"
    )


class PositionLevel(ConceptBase):
    """직급 레벨"""

    level: int = Field(..., description="레벨 (높을수록 상위)")
    includes: list[str] = Field(default_factory=list, description="포함된 직급 목록")


class PositionHierarchy(BaseModel):
    """직급 계층 구조"""

    description: str | None = None
    hierarchy: list[PositionLevel] = Field(default_factory=list)
    expansion_rule: str | None = None


class ConceptsDefinition(BaseModel):
    """전체 개념 정의"""

    skill_categories: list["SkillCategory"] = Field(
        default_factory=list, alias="SkillCategory"
    )
    position_level: PositionHierarchy | None = Field(
        default=None, alias="PositionLevel"
    )


class RelationDefinition(BaseModel):
    """관계 타입 정의"""

    description: str
    direction: str | None = None
    transitive: bool = False
    examples: list[list[str]] = Field(default_factory=list)


class OntologySchemaResponse(BaseModel):
    """온톨로지 스키마 응답"""

    meta: dict[str, Any] = Field(..., alias="_meta")
    relations: dict[str, RelationDefinition]
    concepts: ConceptsDefinition
    expansion_rules: dict[str, Any]
