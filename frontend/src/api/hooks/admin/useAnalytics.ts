import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../client';
import type {
  ProjectionStatus,
  CommunityDetectResponse,
  CommunityDetectParams,
  SimilarEmployeesParams,
  SimilarEmployeesResponse,
  TeamRecommendParams,
  TeamRecommendResponse,
  DeleteProjectionResponse,
} from '@/types/admin';

const PROJECTION_STALE_TIME = 30000; // 30 seconds

// Projection
export function useProjectionStatus() {
  return useQuery({
    queryKey: ['projection-status'],
    queryFn: async (): Promise<ProjectionStatus> => {
      const response = await apiClient.get<ProjectionStatus>('/analytics/projection/status');
      return response.data;
    },
    staleTime: PROJECTION_STALE_TIME,
  });
}

export function useCreateProjection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (minSharedSkills: number = 2): Promise<ProjectionStatus> => {
      const response = await apiClient.post<ProjectionStatus>(
        `/analytics/projection/create?min_shared_skills=${minSharedSkills}`
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projection-status'] });
    },
  });
}

export function useDeleteProjection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (): Promise<DeleteProjectionResponse> => {
      const response = await apiClient.delete<DeleteProjectionResponse>('/analytics/projection');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projection-status'] });
    },
  });
}

// Community Detection
export function useDetectCommunities() {
  return useMutation({
    mutationFn: async (params: CommunityDetectParams = {}): Promise<CommunityDetectResponse> => {
      const response = await apiClient.post<CommunityDetectResponse>('/analytics/communities/detect', params);
      return response.data;
    },
  });
}

// Similar Employees
export function useFindSimilarEmployees() {
  return useMutation({
    mutationFn: async (params: SimilarEmployeesParams): Promise<SimilarEmployeesResponse> => {
      const response = await apiClient.post<SimilarEmployeesResponse>('/analytics/employees/similar', params);
      return response.data;
    },
  });
}

// Team Recommendation
export function useRecommendTeam() {
  return useMutation({
    mutationFn: async (params: TeamRecommendParams): Promise<TeamRecommendResponse> => {
      const response = await apiClient.post<TeamRecommendResponse>('/analytics/team/recommend', params);
      return response.data;
    },
  });
}
