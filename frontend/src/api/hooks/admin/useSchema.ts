import { useQuery } from '@tanstack/react-query';
import apiClient from '../../client';

const SCHEMA_STALE_TIME = 60000; // 1 minute

export interface SchemaNode {
  id: string;
  label: string;
  name: string;
  properties: Record<string, unknown>;
  group: string;
}

export interface SchemaEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface SchemaVisualizationResponse {
  success: boolean;
  nodes: SchemaNode[];
  edges: SchemaEdge[];
}

export function useSchema() {
  return useQuery({
    queryKey: ['schema'],
    queryFn: async (): Promise<SchemaVisualizationResponse> => {
      const response = await apiClient.get<SchemaVisualizationResponse>('/visualization/schema');
      return response.data;
    },
    staleTime: SCHEMA_STALE_TIME,
  });
}
