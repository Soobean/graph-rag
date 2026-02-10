import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../client';
import { buildSearchParams } from '../../utils';
import type {
  Proposal,
  ProposalDetail,
  ProposalListResponse,
  ProposalApproveRequest,
  ProposalRejectRequest,
  BatchOperationResponse,
  OntologyStats,
} from '@/types/admin';

export interface ProposalListParams {
  status?: 'pending' | 'approved' | 'rejected' | 'auto_approved' | 'all';
  proposal_type?: 'NEW_CONCEPT' | 'NEW_SYNONYM' | 'NEW_RELATION' | 'all';
  source?: 'chat' | 'background' | 'admin' | 'all';
  category?: string;
  term_search?: string;
  sort_by?: 'created_at' | 'frequency' | 'confidence';
  sort_order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

const STATS_STALE_TIME = 30000; // 30 seconds

export function useProposalList(params: ProposalListParams = {}) {
  return useQuery({
    queryKey: ['proposals', params],
    queryFn: async (): Promise<ProposalListResponse> => {
      const query = buildSearchParams(params as Record<string, string | number | undefined>);
      const response = await apiClient.get<ProposalListResponse>(
        `/ontology/admin/proposals?${query}`
      );
      return response.data;
    },
  });
}

export function useProposalDetail(proposalId: string | null) {
  return useQuery({
    queryKey: ['proposal', proposalId],
    queryFn: async (): Promise<ProposalDetail> => {
      const response = await apiClient.get<ProposalDetail>(
        `/ontology/admin/proposals/${proposalId}`
      );
      return response.data;
    },
    enabled: !!proposalId,
  });
}

export function useOntologyStats() {
  return useQuery({
    queryKey: ['ontology-stats'],
    queryFn: async (): Promise<OntologyStats> => {
      const response = await apiClient.get<OntologyStats>('/ontology/admin/stats');
      return response.data;
    },
    staleTime: STATS_STALE_TIME,
  });
}

export function useApproveProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      proposalId,
      request,
    }: {
      proposalId: string;
      request: ProposalApproveRequest;
    }): Promise<Proposal> => {
      const response = await apiClient.post<Proposal>(
        `/ontology/admin/proposals/${proposalId}/approve`,
        request
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals'] });
      queryClient.invalidateQueries({ queryKey: ['ontology-stats'] });
    },
  });
}

export function useRejectProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      proposalId,
      request,
    }: {
      proposalId: string;
      request: ProposalRejectRequest;
    }): Promise<Proposal> => {
      const response = await apiClient.post<Proposal>(
        `/ontology/admin/proposals/${proposalId}/reject`,
        request
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals'] });
      queryClient.invalidateQueries({ queryKey: ['ontology-stats'] });
    },
  });
}

export function useBatchApprove() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      proposal_ids,
      note,
    }: {
      proposal_ids: string[];
      note?: string;
    }): Promise<BatchOperationResponse> => {
      const response = await apiClient.post<BatchOperationResponse>(
        '/ontology/admin/proposals/batch-approve',
        { proposal_ids, note }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals'] });
      queryClient.invalidateQueries({ queryKey: ['ontology-stats'] });
    },
  });
}

export function useBatchReject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      proposal_ids,
      reason,
    }: {
      proposal_ids: string[];
      reason: string;
    }): Promise<BatchOperationResponse> => {
      const response = await apiClient.post<BatchOperationResponse>(
        '/ontology/admin/proposals/batch-reject',
        { proposal_ids, reason }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals'] });
      queryClient.invalidateQueries({ queryKey: ['ontology-stats'] });
    },
  });
}
