import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { DeletionImpactPreview } from './DeletionImpactPreview';
import { useDeletionImpact, useDeleteNode } from '@/api/hooks/admin/useGraphEdit';
import { getApiErrorMessage } from '@/api/utils';
import type { NodeResponse } from '@/types/graphEdit';

interface DeleteNodeDialogProps {
  node: NodeResponse | null;
  onOpenChange: (open: boolean) => void;
  previewOnly?: boolean;
  onSuccess?: () => void;
}

function DeleteNodeContent({
  node,
  onOpenChange,
  previewOnly = false,
  onSuccess,
}: {
  node: NodeResponse;
  onOpenChange: (open: boolean) => void;
  previewOnly?: boolean;
  onSuccess?: () => void;
}) {
  const { data: impact, isLoading: impactLoading } = useDeletionImpact(node.id);
  const deleteNode = useDeleteNode();
  const [error, setError] = useState<string | null>(null);

  const hasRelationships = (impact?.affected_relationships.length ?? 0) > 0;

  const handleDelete = (force: boolean) => {
    setError(null);
    deleteNode.mutate(
      { nodeId: node.id, force },
      {
        onSuccess: () => {
          onSuccess?.();
          onOpenChange(false);
        },
        onError: (err) => {
          setError(getApiErrorMessage(err));
        },
      }
    );
  };

  const nodeName = String(node.properties.name || node.id);

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {previewOnly ? 'Deletion Impact Preview' : 'Delete Node'}
        </DialogTitle>
        <DialogDescription>
          {previewOnly
            ? `Impact preview for deleting "${nodeName}"`
            : `Are you sure you want to delete "${nodeName}"? This action cannot be undone.`}
        </DialogDescription>
      </DialogHeader>

      <div className="py-2">
        {impactLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-sm text-muted-foreground">Analyzing impact...</span>
          </div>
        ) : impact ? (
          <DeletionImpactPreview impact={impact} />
        ) : null}

        {error && (
          <div className="mt-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {error}
          </div>
        )}
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          {previewOnly ? 'Close' : 'Cancel'}
        </Button>
        {!previewOnly && (
          hasRelationships ? (
            <Button
              variant="destructive"
              onClick={() => handleDelete(true)}
              disabled={impactLoading || deleteNode.isPending}
            >
              {deleteNode.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Force Delete (with relationships)'
              )}
            </Button>
          ) : (
            <Button
              variant="destructive"
              onClick={() => handleDelete(false)}
              disabled={impactLoading || deleteNode.isPending}
            >
              {deleteNode.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete Node'
              )}
            </Button>
          )
        )}
      </DialogFooter>
    </>
  );
}

export function DeleteNodeDialog({ node, onOpenChange, previewOnly = false, onSuccess }: DeleteNodeDialogProps) {
  return (
    <Dialog open={!!node} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        {node && (
          <DeleteNodeContent
            key={node.id}
            node={node}
            onOpenChange={onOpenChange}
            previewOnly={previewOnly}
            onSuccess={onSuccess}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
