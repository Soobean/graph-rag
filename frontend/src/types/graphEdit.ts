// Graph Edit API Types — mirrors src/api/schemas/graph_edit.py

// ============================================
// Request Types
// ============================================

export interface CreateNodeRequest {
  label: string;
  properties: Record<string, unknown>;
}

export interface UpdateNodeRequest {
  properties: Record<string, unknown>;
}

export interface CreateEdgeRequest {
  source_id: string;
  target_id: string;
  relationship_type: string;
  properties?: Record<string, unknown> | null;
}

export interface RenameImpactRequest {
  new_name: string;
}

// ============================================
// Response Types
// ============================================

export interface NodeResponse {
  id: string;
  labels: string[];
  properties: Record<string, unknown>;
}

export interface NodeListResponse {
  nodes: NodeResponse[];
  count: number;
}

export interface EdgeResponse {
  id: string;
  type: string;
  source_id: string;
  target_id: string;
  properties: Record<string, unknown>;
}

export interface RelationshipCombo {
  source: string;
  target: string;
}

export interface SchemaInfoResponse {
  allowed_labels: string[];
  required_properties: Record<string, string[]>;
  valid_relationships: Record<string, RelationshipCombo[]>;
}

// ============================================
// Impact Analysis Types
// ============================================

export interface AffectedRelationship {
  id: string;
  type: string;
  direction: string;
  connected_node_id: string;
  connected_node_labels: string[];
  connected_node_name: string;
}

export interface ConceptBridgeImpact {
  current_concept: string | null;
  current_hierarchy: string[];
  will_break: boolean;
  new_concept?: string | null;
  new_hierarchy?: string[];
}

export interface DownstreamEffect {
  system: string;
  description: string;
}

export interface NodeDeletionImpactResponse {
  node_id: string;
  node_labels: string[];
  node_name: string;
  affected_relationships: AffectedRelationship[];
  relationship_count: number;
  concept_bridge: ConceptBridgeImpact | null;
  downstream_effects: DownstreamEffect[];
  summary: string;
}

export interface RenameImpactResponse {
  node_id: string;
  node_labels: string[];
  current_name: string;
  new_name: string;
  has_duplicate: boolean;
  concept_bridge: ConceptBridgeImpact | null;
  downstream_effects: DownstreamEffect[];
  summary: string;
}

// ============================================
// Search Params
// ============================================

export interface NodeSearchParams {
  label?: string;
  search?: string;
  limit?: number;
}
