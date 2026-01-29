import { useMutation } from '@tanstack/react-query';
import apiClient from '../client';
import type { QueryRequest, QueryResponse } from '../../types/api';

interface UseQueryApiOptions {
  onSuccess?: (data: QueryResponse) => void;
  onError?: (error: Error) => void;
}

export function useQueryApi(options?: UseQueryApiOptions) {
  return useMutation({
    mutationFn: async (request: QueryRequest): Promise<QueryResponse> => {
      const response = await apiClient.post<QueryResponse>('/query', {
        question: request.question,
        session_id: request.session_id,
        include_explanation: request.include_explanation ?? true,
        include_graph: request.include_graph ?? true,
        graph_limit: request.graph_limit ?? 50,
      });
      return response.data;
    },
    onSuccess: options?.onSuccess,
    onError: options?.onError,
  });
}

export default useQueryApi;
