import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ProposalFilters } from '@/components/admin/ontology/ProposalFilters';
import { ProposalList } from '@/components/admin/ontology/ProposalList';
import { ProposalActions } from '@/components/admin/ontology/ProposalActions';
import { OntologyStats } from '@/components/admin/ontology/OntologyStats';
import {
  useProposalList,
  useApproveProposal,
  useRejectProposal,
  useBatchApprove,
  useBatchReject,
  type ProposalListParams,
} from '@/api/hooks/admin/useOntologyAdmin';
import type { Proposal, PaginationMeta } from '@/types/admin';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const DEFAULT_PAGINATION: PaginationMeta = {
  total: 0,
  page: 1,
  page_size: 20,
  total_pages: 0,
  has_next: false,
  has_prev: false,
};

export function OntologyPage() {
  const [filters, setFilters] = useState<ProposalListParams>({
    status: 'pending',
    sort_by: 'created_at',
    sort_order: 'desc',
    page: 1,
    page_size: 20,
  });
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [pendingReject, setPendingReject] = useState<Proposal | null>(null);

  const { data, isLoading } = useProposalList(filters);
  const approveProposal = useApproveProposal();
  const rejectProposal = useRejectProposal();
  const batchApprove = useBatchApprove();
  const batchReject = useBatchReject();

  const handleApprove = (proposal: Proposal) => {
    approveProposal.mutate({
      proposalId: proposal.id,
      request: { expected_version: proposal.version },
    });
  };

  const handleRejectClick = (proposal: Proposal) => {
    setPendingReject(proposal);
    setRejectReason('');
    setRejectDialogOpen(true);
  };

  const handleRejectConfirm = () => {
    if (pendingReject && rejectReason.trim()) {
      rejectProposal.mutate(
        {
          proposalId: pendingReject.id,
          request: {
            expected_version: pendingReject.version,
            reason: rejectReason.trim(),
          },
        },
        {
          onSuccess: () => {
            setRejectDialogOpen(false);
            setPendingReject(null);
            setRejectReason('');
          },
        }
      );
    }
  };

  const handleBatchApprove = () => {
    batchApprove.mutate(
      { proposal_ids: selectedIds },
      {
        onSuccess: () => setSelectedIds([]),
      }
    );
  };

  const handleBatchRejectClick = () => {
    setRejectReason('');
    setRejectDialogOpen(true);
    setPendingReject(null); // null means batch reject
  };

  const handleBatchRejectConfirm = () => {
    if (rejectReason.trim()) {
      batchReject.mutate(
        { proposal_ids: selectedIds, reason: rejectReason.trim() },
        {
          onSuccess: () => {
            setSelectedIds([]);
            setRejectDialogOpen(false);
            setRejectReason('');
          },
        }
      );
    }
  };

  const handlePageChange = (page: number) => {
    setFilters({ ...filters, page });
    setSelectedIds([]);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Ontology Management</h1>
        <p className="text-muted-foreground">Review and manage ontology proposals</p>
      </div>

      {/* Stats */}
      <OntologyStats />

      {/* Proposals */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-lg">Proposals</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ProposalFilters filters={filters} onFiltersChange={setFilters} />

          <ProposalActions
            selectedCount={selectedIds.length}
            onBatchApprove={handleBatchApprove}
            onBatchReject={handleBatchRejectClick}
            isApproving={batchApprove.isPending}
            isRejecting={batchReject.isPending}
          />

          <ProposalList
            proposals={data?.items || []}
            pagination={data?.pagination || DEFAULT_PAGINATION}
            isLoading={isLoading}
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
            onPageChange={handlePageChange}
            onApprove={handleApprove}
            onReject={handleRejectClick}
            isApproving={approveProposal.isPending}
            isRejecting={rejectProposal.isPending}
          />
        </CardContent>
      </Card>

      {/* Reject Dialog */}
      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Proposal</DialogTitle>
            <DialogDescription>
              {pendingReject
                ? `Rejecting proposal for "${pendingReject.term}"`
                : `Rejecting ${selectedIds.length} selected proposals`}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <label htmlFor="reason" className="block text-sm font-medium mb-2">
              Rejection Reason (required)
            </label>
            <Input
              id="reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Enter reason for rejection..."
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={pendingReject ? handleRejectConfirm : handleBatchRejectConfirm}
              disabled={!rejectReason.trim() || rejectProposal.isPending || batchReject.isPending}
            >
              Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
