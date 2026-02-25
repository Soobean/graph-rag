import { useQuery, useMutation } from '@tanstack/react-query';
import apiClient from '../../client';
import type {
  ProjectListResponse,
  SkillCategoryListResponse,
  FindCandidatesRequest,
  FindCandidatesResponse,
  StaffingPlanRequest,
  StaffingPlanResponse,
  BudgetAnalysisRequest,
  BudgetAnalysisResponse,
} from '@/types/admin';

const STALE_TIME = 5 * 60 * 1000; // 5 minutes

// ============================================
// Queries
// ============================================

export function useStaffingProjects() {
  return useQuery({
    queryKey: ['staffing-projects'],
    queryFn: async (): Promise<ProjectListResponse> => {
      const response = await apiClient.get<ProjectListResponse>(
        '/analytics/staffing/projects'
      );
      return response.data;
    },
    staleTime: STALE_TIME,
  });
}

export function useStaffingCategories(projectName?: string) {
  return useQuery({
    queryKey: ['staffing-categories', projectName],
    queryFn: async (): Promise<SkillCategoryListResponse> => {
      const params = projectName ? { project_name: projectName } : {};
      const response = await apiClient.get<SkillCategoryListResponse>(
        '/analytics/staffing/categories',
        { params }
      );
      return response.data;
    },
    enabled: !!projectName,
    staleTime: STALE_TIME,
  });
}

// ============================================
// Mutations
// ============================================

export function useFindCandidates() {
  return useMutation({
    mutationFn: async (
      params: FindCandidatesRequest
    ): Promise<FindCandidatesResponse> => {
      const response = await apiClient.post<FindCandidatesResponse>(
        '/analytics/staffing/find-candidates',
        params
      );
      return response.data;
    },
  });
}

export function useGenerateStaffingPlan() {
  return useMutation({
    mutationFn: async (
      params: StaffingPlanRequest
    ): Promise<StaffingPlanResponse> => {
      const response = await apiClient.post<StaffingPlanResponse>(
        '/analytics/staffing/plan',
        params
      );
      return response.data;
    },
  });
}

export function useAnalyzeBudget() {
  return useMutation({
    mutationFn: async (
      params: BudgetAnalysisRequest
    ): Promise<BudgetAnalysisResponse> => {
      const response = await apiClient.post<BudgetAnalysisResponse>(
        '/analytics/staffing/budget-analysis',
        params
      );
      return response.data;
    },
  });
}
