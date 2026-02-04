import { useQuery, useMutation } from '@tanstack/react-query';
import apiClient from '../../client';
import type {
  SkillGapAnalyzeRequest,
  SkillGapAnalyzeResponse,
  SkillRecommendRequest,
  SkillRecommendResponse,
} from '@/types/admin';

const CATEGORIES_STALE_TIME = 5 * 60 * 1000; // 5 minutes

export function useSkillCategories() {
  return useQuery({
    queryKey: ['skill-categories'],
    queryFn: async (): Promise<string[]> => {
      const response = await apiClient.get<string[]>('/analytics/skill-gap/categories');
      return response.data;
    },
    staleTime: CATEGORIES_STALE_TIME,
  });
}

export function useAnalyzeSkillGap() {
  return useMutation({
    mutationFn: async (params: SkillGapAnalyzeRequest): Promise<SkillGapAnalyzeResponse> => {
      const response = await apiClient.post<SkillGapAnalyzeResponse>(
        '/analytics/skill-gap/analyze',
        params
      );
      return response.data;
    },
  });
}

export function useRecommendGapSolution() {
  return useMutation({
    mutationFn: async (params: SkillRecommendRequest): Promise<SkillRecommendResponse> => {
      const response = await apiClient.post<SkillRecommendResponse>(
        '/analytics/skill-gap/recommend',
        params
      );
      return response.data;
    },
  });
}
