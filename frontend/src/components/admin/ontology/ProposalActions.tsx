import { Button } from '@/components/ui/button';
import { Check, X, Loader2 } from 'lucide-react';

interface ProposalActionsProps {
  selectedCount: number;
  onBatchApprove: () => void;
  onBatchReject: () => void;
  isApproving: boolean;
  isRejecting: boolean;
}

export function ProposalActions({
  selectedCount,
  onBatchApprove,
  onBatchReject,
  isApproving,
  isRejecting,
}: ProposalActionsProps) {
  if (selectedCount === 0) return null;

  return (
    <div className="flex items-center gap-3 rounded-lg bg-muted/50 px-4 py-3">
      <span className="text-sm font-medium">{selectedCount} selected</span>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          className="text-green-600 hover:text-green-700 hover:bg-green-50"
          onClick={onBatchApprove}
          disabled={isApproving || isRejecting}
        >
          {isApproving ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Check className="mr-2 h-4 w-4" />
          )}
          Approve All
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="text-red-600 hover:text-red-700 hover:bg-red-50"
          onClick={onBatchReject}
          disabled={isApproving || isRejecting}
        >
          {isRejecting ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <X className="mr-2 h-4 w-4" />
          )}
          Reject All
        </Button>
      </div>
    </div>
  );
}
