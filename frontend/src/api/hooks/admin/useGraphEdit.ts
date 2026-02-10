import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../client';
import { buildSearchParams } from '../../utils';
import type {
  NodeResponse,
  NodeListResponse,
  EdgeResponse,
  SchemaInfoResponse,
  CreateNodeRequest,
  UpdateNodeRequest,
  CreateEdgeRequest,
  RenameImpactRequest,
  NodeDeletionImpactResponse,
  RenameImpactResponse,
  NodeSearchParams,
} from '@/types/graphEdit';

const SCHEMA_STALE_TIME = 5 * 60 * 1000; // 5 minutes
const NODE_SEARCH_STALE_TIME = 30 * 1000; // 30 seconds
const IMPACT_STALE_TIME = 60 * 1000; // 1 minute

function encodeNodeId(nodeId: string): string {
  return encodeURIComponent(nodeId);
}

export function useSchemaInfo() {
  return useQuery({
    queryKey: ['graph-schema'],
    queryFn: async (): Promise<SchemaInfoResponse> => {
      const response = await apiClient.get<SchemaInfoResponse>('/graph/schema/labels');
      return response.data;
    },
    staleTime: SCHEMA_STALE_TIME,
  });
}

export function useNodeSearch(params: NodeSearchParams = {}, enabled = true) {
  return useQuery({
    queryKey: ['graph-nodes', params],
    queryFn: async (): Promise<NodeListResponse> => {
      const query = buildSearchParams(params as Record<string, string | number | undefined>);
      const response = await apiClient.get<NodeListResponse>(`/graph/nodes?${query}`);
      return response.data;
    },
    enabled,
    staleTime: NODE_SEARCH_STALE_TIME,
  });
}

export function useCreateNode() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: CreateNodeRequest): Promise<NodeResponse> => {
      const response = await apiClient.post<NodeResponse>('/graph/nodes', request);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['graph-nodes'] });
    },
  });
}

export function useUpdateNode() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      nodeId,
      request,
    }: {
      nodeId: string;
      request: UpdateNodeRequest;
    }): Promise<NodeResponse> => {
      const response = await apiClient.patch<NodeResponse>(
        `/graph/nodes/${encodeNodeId(nodeId)}`,
        request
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['graph-nodes'] });
    },
  });
}

export function useDeleteNode() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      nodeId,
      force = false,
    }: {
      nodeId: string;
      force?: boolean;
    }): Promise<void> => {
      await apiClient.delete(`/graph/nodes/${encodeNodeId(nodeId)}?force=${force}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['graph-nodes'] });
      queryClient.invalidateQueries({ queryKey: ['graph-deletion-impact'] });
    },
  });
}

export function useDeletionImpact(nodeId: string | null) {
  return useQuery({
    queryKey: ['graph-deletion-impact', nodeId],
    queryFn: async (): Promise<NodeDeletionImpactResponse> => {
      const response = await apiClient.get<NodeDeletionImpactResponse>(
        `/graph/nodes/${encodeNodeId(nodeId!)}/impact`
      );
      return response.data;
    },
    enabled: !!nodeId,
    staleTime: IMPACT_STALE_TIME,
  });
}

export function useRenameImpact() {
  return useMutation({
    mutationFn: async ({
      nodeId,
      ...body
    }: {
      nodeId: string;
    } & RenameImpactRequest): Promise<RenameImpactResponse> => {
      const response = await apiClient.post<RenameImpactResponse>(
        `/graph/nodes/${encodeNodeId(nodeId)}/impact/rename`,
        body
      );
      return response.data;
    },
  });
}

export function useCreateEdge() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: CreateEdgeRequest): Promise<EdgeResponse> => {
      const response = await apiClient.post<EdgeResponse>('/graph/edges', request);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['graph-nodes'] });
    },
  });
}

export function useDeleteEdge() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (edgeId: string): Promise<void> => {
      await apiClient.delete(`/graph/edges/${encodeURIComponent(edgeId)}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['graph-nodes'] });
    },
  });
}
