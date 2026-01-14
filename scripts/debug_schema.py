from src.api.schemas.ontology import ConceptsDefinition, OntologySchemaResponse

print("Import successful")
try:
    print(ConceptsDefinition.model_json_schema())
except Exception as e:
    print(f"Error in ConceptsDefinition: {e}")

try:
    print(OntologySchemaResponse.model_json_schema())
except Exception as e:
    print(f"Error in OntologySchemaResponse: {e}")
