// API 요청/응답 타입 정의

export interface QueryRequest {
  question: string;
  session_id?: string;
  include_explanation?: boolean;
  include_graph?: boolean;
  graph_limit?: number;
}

export interface QueryResponse {
  success: boolean;
  question: string;
  response: string;
  metadata?: QueryMetadata;
  explanation?: ExplainableResponse;
  error?: string;
}

export interface QueryMetadata {
  intent: string;
  intent_confidence: number;
  entities: Record<string, string[]>;
  cypher_query?: string;
  result_count: number;
  execution_path: string[];
}

export interface ExplainableResponse {
  thought_process: ThoughtProcessVisualization | null;
  graph_data: ExplainableGraphData | null;
}

export interface ThoughtProcessVisualization {
  steps: ThoughtStep[];
  concept_expansions: ConceptExpansionTree[];
  total_duration_ms?: number;
  execution_path: string[];
}

export interface ThoughtStep {
  step_number: number;
  node_name: string;
  step_type: StepType;
  description: string;
  input_summary?: string;
  output_summary?: string;
  details: Record<string, unknown>;
  duration_ms?: number;
}

export type StepType =
  | 'classification'
  | 'decomposition'
  | 'extraction'
  | 'expansion'
  | 'resolution'
  | 'generation'
  | 'execution'
  | 'response'
  | 'cache';

export interface ConceptExpansionTree {
  original_concept: string;
  entity_type: string;
  expansion_strategy: 'strict' | 'normal' | 'broad';
  expanded_concepts: string[];
  expansion_path: ExpansionPath[];
}

export interface ExpansionPath {
  from: string;
  to: string;
  relation: string;
}

export interface ExplainableGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  node_count: number;
  edge_count: number;
  query_entity_ids: string[];
  expanded_entity_ids: string[];
  result_entity_ids: string[];
  has_more: boolean;
}

export interface GraphNode {
  id: string;
  label: string;
  name: string;
  properties: Record<string, unknown>;
  group?: string;
  role?: 'start' | 'intermediate' | 'end';
  depth: number;
  style: NodeStyle;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface NodeStyle {
  color: string;
  icon: string;
  size: number;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  version: string;
  neo4j_connected: boolean;
}

// SSE Streaming Types
export interface StreamingMetadata {
  intent: string;
  intent_confidence: number;
  entities: Record<string, string[]>;
  cypher_query: string;
  result_count: number;
  execution_path: string[];
}

export type StreamingEventType = 'metadata' | 'chunk' | 'done' | 'error';

export interface StreamingMetadataEvent {
  type: 'metadata';
  data: StreamingMetadata;
}

export interface StreamingChunkEvent {
  type: 'chunk';
  text: string;
}

export interface StreamingDoneEvent {
  type: 'done';
  success: boolean;
  full_response: string;
}

export interface StreamingErrorEvent {
  type: 'error';
  message: string;
}

export type StreamingEvent =
  | StreamingMetadataEvent
  | StreamingChunkEvent
  | StreamingDoneEvent
  | StreamingErrorEvent;
