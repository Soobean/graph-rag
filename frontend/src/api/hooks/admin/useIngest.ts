import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../client';
import type { IngestRequest, IngestJob, IngestResponse, FileUploadResponse } from '@/types/admin';

const JOBS_REFETCH_INTERVAL = 5000; // 5 seconds
const RUNNING_JOB_REFETCH_INTERVAL = 2000; // 2 seconds

export function useIngestJobs(limit: number = 20) {
  return useQuery({
    queryKey: ['ingest-jobs', limit],
    queryFn: async (): Promise<IngestJob[]> => {
      const response = await apiClient.get<IngestJob[]>(`/ingest?limit=${limit}`);
      return response.data;
    },
    refetchInterval: JOBS_REFETCH_INTERVAL,
  });
}

export function useIngestJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ['ingest-job', jobId],
    queryFn: async (): Promise<IngestJob> => {
      const response = await apiClient.get<IngestJob>(`/ingest/${jobId}`);
      return response.data;
    },
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && (data.status === 'pending' || data.status === 'running')) {
        return RUNNING_JOB_REFETCH_INTERVAL;
      }
      return false;
    },
  });
}

export function useStartIngest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: IngestRequest): Promise<IngestResponse> => {
      const response = await apiClient.post<IngestResponse>('/ingest', request);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ingest-jobs'] });
    },
  });
}

export function useUploadFile() {
  return useMutation({
    mutationFn: async (file: File): Promise<FileUploadResponse> => {
      const formData = new FormData();
      formData.append('file', file);

      const response = await apiClient.post<FileUploadResponse>('/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return response.data;
    },
  });
}
