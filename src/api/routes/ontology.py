from fastapi import APIRouter, HTTPException

from src.api.schemas.ontology import OntologySchemaResponse
from src.domain.ontology.loader import get_ontology_loader

router = APIRouter(prefix="/api/v1/ontology", tags=["ontology"])


@router.get("/schema", response_model=OntologySchemaResponse)
async def get_ontology_schema() -> dict:
    """
    온톨로지 스키마 조회 (Palantir Object Explorer용)

    정의된 개념(Concept), 관계(Relation), 그리고 스타일 메타데이터를 반환합니다.
    이 정보를 사용하여 프론트엔드에서 동적으로 필터/아이콘/색상을 렌더링할 수 있습니다.
    """
    try:
        loader = get_ontology_loader()
        schema = loader.load_schema()
        return schema
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load ontology schema: {e}"
        )


@router.get("/concept/{category}/{name}/style")
async def get_concept_style(category: str, name: str) -> dict:
    """특정 개념의 스타일 조회"""
    try:
        loader = get_ontology_loader()
        # 카테고리 매핑 (API path -> internal enum value if needed, currently string match)
        # category: "skills" or "positions"
        style = loader.get_style_for_concept(name, category)
        if style:
            return style

        # 기본 스타일 반환
        return {"color": "#94A3B8", "icon": "circle"}  # Slate-400
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
