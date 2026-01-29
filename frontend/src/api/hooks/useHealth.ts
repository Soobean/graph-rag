import { useQuery } from '@tanstack/react-query';
import apiClient from '../client';
import type { HealthResponse } from '../../types/api';

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async (): Promise<HealthResponse> => {
      const response = await apiClient.get<HealthResponse>('/health');
      return response.data;
    },
    refetchInterval: 30000, // 30초마다 헬스체크
    staleTime: 10000,
  });
}

export default useHealth;
