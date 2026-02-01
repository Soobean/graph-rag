import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Check, X, Loader2, ChevronLeft, ChevronRight } from 'lucide-react';
import type { Proposal, PaginationMeta, ProposalStatus, ProposalType, ProposalSource } from '@/types/admin';

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function getStatusBadge(status: ProposalStatus | string) {
  switch (status) {
    case 'pending':
      return <Badge variant="warning">Pending</Badge>;
    case 'approved':
      return <Badge variant="success">Approved</Badge>;
    case 'auto_approved':
      return <Badge variant="success">Auto-Approved</Badge>;
    case 'rejected':
      return <Badge variant="destructive">Rejected</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

function getTypeBadge(type: ProposalType | string) {
  switch (type) {
    case 'NEW_CONCEPT':
      return <Badge variant="default">Concept</Badge>;
    case 'NEW_SYNONYM':
      return <Badge variant="secondary">Synonym</Badge>;
    case 'NEW_RELATION':
      return <Badge variant="outline">Relation</Badge>;
    default:
      return <Badge variant="outline">{type}</Badge>;
  }
}

function getSourceBadge(source: ProposalSource | string) {
  switch (source) {
    case 'chat':
      return <Badge variant="default" className="bg-blue-500">Chat</Badge>;
    case 'background':
      return <Badge variant="secondary">Background</Badge>;
    case 'admin':
      return <Badge variant="outline" className="border-purple-500 text-purple-600">Admin</Badge>;
    default:
      return <Badge variant="outline">{source}</Badge>;
  }
}

interface ProposalListProps {
  proposals: Proposal[];
  pagination: PaginationMeta;
  isLoading: boolean;
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
  onPageChange: (page: number) => void;
  onApprove: (proposal: Proposal) => void;
  onReject: (proposal: Proposal) => void;
  isApproving: boolean;
  isRejecting: boolean;
}

export function ProposalList({
  proposals,
  pagination,
  isLoading,
  selectedIds,
  onSelectionChange,
  onPageChange,
  onApprove,
  onReject,
  isApproving,
  isRejecting,
}: ProposalListProps) {
  const allSelected = proposals.length > 0 && proposals.every((p) => selectedIds.includes(p.id));

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      onSelectionChange(proposals.filter((p) => p.status === 'pending').map((p) => p.id));
    } else {
      onSelectionChange([]);
    }
  };

  const handleSelectOne = (id: string, checked: boolean) => {
    if (checked) {
      onSelectionChange([...selectedIds, id]);
    } else {
      onSelectionChange(selectedIds.filter((i) => i !== id));
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (proposals.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <p>No proposals found</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">
              <Checkbox checked={allSelected} onCheckedChange={handleSelectAll} />
            </TableHead>
            <TableHead>Term</TableHead>
            <TableHead>Category</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Frequency</TableHead>
            <TableHead className="text-right">Confidence</TableHead>
            <TableHead>Created</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {proposals.map((proposal) => (
            <TableRow key={proposal.id}>
              <TableCell>
                {proposal.status === 'pending' && (
                  <Checkbox
                    checked={selectedIds.includes(proposal.id)}
                    onCheckedChange={(checked) => handleSelectOne(proposal.id, checked as boolean)}
                  />
                )}
              </TableCell>
              <TableCell className="font-medium">{proposal.term}</TableCell>
              <TableCell>
                <span className="text-sm text-muted-foreground">{proposal.category}</span>
              </TableCell>
              <TableCell>{getTypeBadge(proposal.proposal_type)}</TableCell>
              <TableCell>{getSourceBadge(proposal.source)}</TableCell>
              <TableCell>{getStatusBadge(proposal.status)}</TableCell>
              <TableCell className="text-right tabular-nums">{proposal.frequency}</TableCell>
              <TableCell className="text-right tabular-nums">{(proposal.confidence * 100).toFixed(0)}%</TableCell>
              <TableCell className="text-sm text-muted-foreground">{formatDate(proposal.created_at)}</TableCell>
              <TableCell className="text-right">
                {proposal.status === 'pending' && (
                  <div className="flex items-center justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-green-600 hover:text-green-700 hover:bg-green-50"
                      onClick={() => onApprove(proposal)}
                      disabled={isApproving || isRejecting}
                    >
                      <Check className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-red-600 hover:text-red-700 hover:bg-red-50"
                      onClick={() => onReject(proposal)}
                      disabled={isApproving || isRejecting}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        {pagination.total > 0 ? (
          <p className="text-sm text-muted-foreground">
            Showing {(pagination.page - 1) * pagination.page_size + 1} to{' '}
            {Math.min(pagination.page * pagination.page_size, pagination.total)} of {pagination.total} results
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">No results</p>
        )}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(pagination.page - 1)}
            disabled={!pagination.has_prev}
          >
            <ChevronLeft className="h-4 w-4" />
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {pagination.page} of {pagination.total_pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(pagination.page + 1)}
            disabled={!pagination.has_next}
          >
            Next
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
