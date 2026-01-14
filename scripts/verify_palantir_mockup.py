import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.domain.ontology.loader import get_ontology_loader, OntologyCategory
from src.api.schemas.visualization import GraphNode, NodeStyle


def verify_styles():
    print("Verifying Ontology Styles...")
    loader = get_ontology_loader()

    # Test cases: (Concept, Category, Expected Color or None)
    test_cases = [
        ("Python", "skills", "#10B981"),  # Backend style
        ("React", "skills", "#F59E0B"),  # Frontend style
        ("Senior", "positions", "#B91C1C"),  # Senior style
        ("Senior Engineer", "positions", "#B91C1C"),  # Included in Senior
        ("UnknownSkill", "skills", None),
    ]

    for concept, category, expected_color in test_cases:
        cat_enum = (
            OntologyCategory.SKILLS
            if category == "skills"
            else OntologyCategory.POSITIONS
        )
        style = loader.get_style_for_concept(concept, cat_enum)

        status = "✅"
        if expected_color:
            if not style or style["color"] != expected_color:
                status = "❌"
                print(
                    f"{status} {concept} ({category}): Expected {expected_color}, got {style}"
                )
            else:
                print(
                    f"{status} {concept} ({category}): Got {style['color']} ({style['icon']})"
                )
        else:
            if style is not None:
                status = "❌"
                print(f"{status} {concept} ({category}): Expected None, got {style}")
            else:
                print(f"{status} {concept} ({category}): Correctly None")


def verify_schema():
    print("\nVerifying GraphNode Schema...")
    try:
        style = NodeStyle(color="#000000", icon="test")
        node = GraphNode(
            id="1", label="Test", name="Test Node", group="test", style=style
        )
        print(f"✅ GraphNode created successfully with style: {node.style}")
    except Exception as e:
        print(f"❌ GraphNode creation failed: {e}")


if __name__ == "__main__":
    verify_styles()
    verify_schema()
