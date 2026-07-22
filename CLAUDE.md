# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Graph RAG - a Retrieval-Augmented Generation system using Neo4j graph database and Azure OpenAI. Users ask natural language questions (Korean/English) about employees, projects, skills, and organizations; the system translates them into Cypher queries via a LangGraph pipeline.

## Commands

### Backend (Python/FastAPI)
```bash
# Run API server (dev mode with hot reload)
uvicorn src.main:app --reload

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_pipeline_integration.py -v

# Run a single test function
pytest tests/test_graph_edit_service.py::test_create_node -v

# Run integration tests only (requires Neo4j)
pytest tests/ -m integration -v

# Lint
ruff check src/ tests/
ruff format --check src/ tests/

# Type check
mypy src/

# Eval Harness (golden-set accuracy — needs live Neo4j + Azure OpenAI, see docs/EVALS.md)
python -m evals.runner              # deterministic scoring, ~5 min
python -m evals.runner --judge      # + LLM faithfulness
python -m evals.runner --verify-refs  # validate reference oracles (no LLM)
```

### Frontend (React/TypeScript)
```bash
cd frontend
npm run dev        # Dev server (port 5173, proxies /api to :8000)
npm run build      # Production build
npm run lint       # ESLint
npm run test       # Vitest (run once)
npm run test:watch # Vitest (watch mode)
```

### Infrastructure
```bash
# Neo4j (required for backend)
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password123 neo4j:5.15-community

# Full stack via Docker (includes GDS and APOC plugins)
docker compose up -d
```

## Architecture

### Backend Pipeline (LangGraph)

The core is `GraphRAGPipeline` in `src/graph/pipeline.py` - a LangGraph `StateGraph` with these nodes:

```
Question → IntentEntityExtractor → ConceptExpander → EntityResolver → CypherGenerator → GraphExecutor → ResponseGenerator
                                                         ↓ (unresolved)
                                                   ClarificationHandler
```

- **State**: `GraphRAGState` (`src/graph/state.py`) - a TypedDict flowing through all nodes. Defines 9 intent types (`personnel_search`, `project_matching`, `relationship_search`, `org_analysis`, `mentoring_network`, `certificate_search`, `path_analysis`, `ontology_update`, `global_analysis`).
- **Nodes**: Each in `src/graph/nodes/` - inherits `BaseNode`, implements `async def process(state) -> dict`
- **Routing**: `route_after_resolver` decides whether to proceed to Cypher or ask for clarification

All 12 pipeline nodes (`src/graph/nodes/`):
| Node | Purpose |
|------|---------|
| `IntentEntityExtractorNode` | Combined intent classification + entity extraction (single LLM call) |
| `ConceptExpanderNode` | Expands entities using ontology synonyms/hierarchy |
| `EntityResolverNode` | Resolves extracted entities against Neo4j |
| `CypherGeneratorNode` | Translates to Cypher (uses `state.entities`, not `resolved_entities`) |
| `GraphExecutorNode` | Executes Cypher against Neo4j |
| `ResponseGeneratorNode` | Synthesizes natural language answer from results |
| `ClarificationHandlerNode` | Generates clarification questions for unresolved entities |
| `CacheCheckerNode` | Vector similarity cache for repeated questions |
| `QueryDecomposerNode` | Multi-hop query decomposition |
| `OntologyLearnerNode` | Generates ontology change proposals from unresolved queries |
| `OntologyUpdateHandlerNode` | Handles user-driven ontology updates |
| `CommunitySummarizerNode` | Global/macro analysis using community detection results |

### Dependency Injection

All services are initialized in `src/main.py` `lifespan()` and stored on `app.state`. FastAPI `Depends()` functions in `src/dependencies.py` pull from `app.state`. Dependency flow:

```
Settings → Infrastructure (Neo4jClient, AzureOpenAIGateway)
  → Repositories (Neo4jRepository) + Application (LLMTaskService)
  → Pipeline (GraphRAGPipeline) + Services (7 services)
```

Tests mock these via `conftest.py` fixtures. Never instantiate services directly in routes.

### Repository Layer

`src/repositories/` contains specialized repositories (split from a monolithic `Neo4jRepository`):

| Repository | Purpose |
|-----------|---------|
| `neo4j_repository.py` | Core Neo4j operations (legacy, still used for Cypher execution) |
| `neo4j_entity_repository.py` | Entity resolution and lookup against Neo4j |
| `neo4j_graph_crud_repository.py` | Node/edge CRUD operations |
| `neo4j_ontology_concept_repository.py` | Concept hierarchy and ontology queries |
| `neo4j_ontology_proposal_repository.py` | Ontology change proposal persistence |
| `neo4j_schema_repository.py` | Graph schema introspection |
| `neo4j_vector_repository.py` | Vector similarity search |
| `query_cache_repository.py` | Query result caching |
| `user_repository.py` | User/auth data |

### LLM Layers (Clean Architecture)

LLM access is split into two layers (formerly a single `LLMRepository` god object):

- **`src/infrastructure/llm/gateway.py`** — `AzureOpenAIGateway`: transport layer. Client management, `generate`/`generate_json`/`generate_stream` primitives, HEAVY→LIGHT fallback policy, embeddings, `ModelTier`, error classification (`classify_api_status_error`).
- **`src/application/llm/task_service.py`** — `LLMTaskService`: use-case layer. Pipeline task methods (`classify_intent_and_extract_entities`, `generate_cypher`, `generate_response`, `generate_response_stream`, `generate_clarification`, `decompose_query`). Loads prompts, formats inputs, picks tier/fallback policy, delegates transport to the gateway.
- **`src/application/llm/formatters.py`** — pure functions for prompt formatting. `format_results()` preserves (subject, relation, object) pairs per row — do NOT regroup by label (past critical bug).

Node wiring: task nodes (intent/cypher/response/clarification/decomposer) take `LLMTaskService`; primitive consumers (cache_checker, ontology_learner, ontology_update_handler, bootstrap extractors) take `AzureOpenAIGateway` directly.

### Cypher Domain Model

- **`src/domain/cypher/corrections.py`** — pure functions that correct LLM-generated Cypher before execution: `fix_not_in_syntax` (SQL-style `NOT IN` → canonical `NOT x IN`), `fix_in_clause_to_tolower` (IN clause → `ANY`/`NONE` + `toLower`), `fix_aggregation_type_a_return`, `correct_parameters`, `coerce_tolower_params`. `CypherGeneratorNode` calls the single entry point `apply_corrections(cypher, parameters, entities)`.
- Order invariant (documented in module docstring): canonicalize before convert — the 2-pass structure is what makes negation handling correct.
- Tests live in `tests/domain/test_cypher_corrections.py`. When a new Cypher correction is needed, add it here (with tests), NOT as a regex in the node.

### Bootstrap Subsystem

`src/bootstrap/` handles automatic schema extraction from uploaded data (separate from both the LangGraph pipeline and ingestion):
- `open_extractor.py` - LLM-based triple extraction (subject-relation-object)
- `relation_normalizer.py` - Normalizes extracted relations to consistent forms
- `schema_generator.py` - Generates graph schema from extracted triples
- Uses confidence-scored `Triple` dataclass (`models.py`) with HIGH/MEDIUM/LOW thresholds

### Two-Label Ontology System

This is the most common source of bugs:
- **`:Skill` nodes** = data layer. `(Employee)-[:HAS_SKILL]->(Skill)`. No IS_A relationships.
- **`:Concept` nodes** = ontology layer. `(Concept)-[:IS_A]->(Concept)` hierarchy.
- **Bridge by name**: `WHERE toLower(concept.name) = toLower(skill.name)`. Never write `(Skill)-[:IS_A]->(Concept)`.
- Synonyms/hierarchy defined in `src/domain/ontology/schema.yaml` and `synonyms.yaml`.
- OntologyRegistry supports 3 loader modes: `yaml`, `neo4j`, `hybrid` (configured via `ONTOLOGY_MODE` env var).

### Services

7 services initialized in `lifespan()`, all on `app.state`:

| Service | File | Notes |
|---------|------|-------|
| `ProjectStaffingService` | `src/services/project_staffing_service.py` | Direct Cypher, bypasses LangGraph |
| `GDSService` | `src/services/gds_service.py` | Neo4j Graph Data Science (community detection, similarity) |
| `GraphEditService` | `src/services/graph_edit_service.py` | CRUD with whitelist-based label/relationship validation |
| `AuthService` | `src/services/auth_service.py` | JWT auth, toggled by `AUTH_ENABLED` (default: off) |
| `OntologyService` | `src/services/ontology_service.py` | Proposal management, approval workflows, versioning |
| `CommunityBatchService` | `src/services/community_batch_service.py` | Background batch jobs for GDS operations |
| `ExplainabilityService` | `src/api/services/explainability.py` | Stateless, formats pipeline execution traces |

### API Routes

All under `/api/v1` prefix. 8 routers registered in `src/main.py`:

| Router | Prefix | Key endpoints |
|--------|--------|---------------|
| `query` | `/query` | `POST /query`, `POST /query/stream`, `GET /health`, `GET /schema` |
| `graph_edit` | `/graph` | CRUD for `/graph/nodes/*`, `/graph/edges/*`, deletion impact preview |
| `visualization` | `/visualization` | Subgraph, community, query-result, query-path rendering data |
| `analytics` | `/analytics` | GDS projections, community detection, similarity, team recommendations |
| `ontology_admin` | `/ontology/admin` | Proposal list/approve/reject, batch operations, stats |
| `community_admin` | `/communities` | Batch community refresh, job status tracking |
| `ingest` | `/ingest` | File upload (CSV/Excel), job status, schema extraction |
| `ontology` | `/ontology` | Read-only ontology info |

### Ingestion Subsystem

`src/ingestion/` is a **separate** data pipeline (not LangGraph). Handles CSV/Excel uploads, entity extraction, and graph loading. Has its own `pipeline.py`, loaders (`csv_loader.py`, `excel_loader.py`), and `extractor.py`.

### Frontend

React 19 + TypeScript + Vite + Tailwind CSS + Zustand state management.

- **Pages**: Chat (`/`), Compare (`/compare`), Staffing (`/staffing`), Admin (`/admin/*`)
- **Admin subroutes**: `/admin/overview`, `/admin/ontology`, `/admin/ingest`, `/admin/analytics`, `/admin/graph-edit` (all lazy-loaded)
- **State**: Zustand stores in `frontend/src/stores/` (chatStore, graphStore, uiStore)
- **API layer**: React Query hooks in `frontend/src/api/hooks/` (general) and `frontend/src/api/hooks/admin/` (admin-specific: `useAnalytics`, `useGraphEdit`, `useIngest`, `useOntologyAdmin`, `useProjectStaffing`)
- **UI components**: shadcn/ui pattern in `frontend/src/components/ui/`
- **Graph visualization**: `@xyflow/react` (React Flow) in `frontend/src/components/graph/`
- **Path alias**: `@/` maps to `frontend/src/`

### Prompt Templates

13 YAML files in `src/prompts/` for LLM instructions. Key ones:
- `intent_entity_combined.yaml` - unified intent + entity extraction (primary)
- `cypher_generation.yaml` - Cypher translation (must include `toLower()` examples)
- `response_generation.yaml` - answer synthesis
- `clarification.yaml` - clarification question generation
- `community_summary.yaml` - community graph summarization

## Critical Patterns

### Neo4j Case Sensitivity
All Cypher queries matching by name MUST use `toLower()`:
```cypher
WHERE toLower(n.name) = toLower($param)
```
For `IN` lists: `ANY(m IN $list WHERE toLower(x.name) = toLower(m))`. For negated lists ("제외" queries): `NONE(m IN $list WHERE toLower(x.name) = toLower(m))` — `src/domain/cypher` auto-corrects both forms.
Python-side comparisons also need `.lower()`. This applies to prompt templates in `src/prompts/` too.

### Korean IME Handling
All React `onKeyDown` handlers with submit-on-Enter MUST guard against IME composition:
```typescript
if (e.nativeEvent.isComposing) return;
```

### Employee Node Duplication
The DB has duplicate Employee nodes (same person, different node IDs). Queries that aggregate per-person data must group by `e.name`, not by node identity.

### Korean Suffix Stripping
LLM may extract "챗봇 리뉴얼 프로젝트" but DB stores "챗봇 리뉴얼". Entity resolution in `Neo4jRepository._strip_korean_suffix()` handles common suffixes (프로젝트, 팀, 부서, 회사, 센터, 연구소, 본부, 사업부).

### Pipeline Routing Detail
`CypherGeneratorNode` uses `state.entities` (raw extracted), NOT `resolved_entities` (Neo4j-matched). Cypher generation can work even with unresolved entities — don't block the pipeline flow on resolution failures.

## Testing

- `asyncio_mode = "auto"` in pyproject.toml - no need for `@pytest.mark.asyncio`
- All tests use mocked repositories (`conftest.py` fixtures: `mock_neo4j`, `mock_llm`, `mock_settings`, `pipeline`)
- Test naming: `test_<behavior>_<condition>`
- DB label is `Employee` (not `Person`)
- 50+ test files covering unit, integration, auth, ontology, and API routes

## Code Style

- **ruff**: line-length 88, target Python 3.12. Rules: E, W, F, I (isort), B (bugbear), C4 (comprehensions), UP (pyupgrade). `E501` ignored (formatter handles it), `B008` ignored (FastAPI `Depends()` pattern).
- **mypy**: strict (`disallow_untyped_defs`, `warn_return_any`), with pydantic plugin. `neo4j.*` and `langgraph.*` have `ignore_missing_imports`.

## Environment

- Python 3.12, managed with `uv` (lockfile: `uv.lock`)
- Node.js for frontend
- Neo4j 5.15 Community on `bolt://localhost:7687`
- Azure OpenAI (not direct OpenAI) - configured via `AZURE_OPENAI_*` env vars
- Config: `cp .env.example .env` then edit
- Auth disabled by default (`AUTH_ENABLED=false`); when off, all APIs are public (demo mode)
