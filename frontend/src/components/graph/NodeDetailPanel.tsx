import { useState, useCallback } from 'react';
import { X, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { EditNodeDialog } from '@/components/admin/graph-edit/EditNodeDialog';
import { DeleteNodeDialog } from '@/components/admin/graph-edit/DeleteNodeDialog';
import { useGraphStore } from '@/stores';
import { cn } from '@/lib/utils';
import type { FlowNode } from '@/types/graph';
import type { NodeResponse } from '@/types/graphEdit';

interface NodeDetailPanelProps {
  className?: string;
}

/** FlowNode → NodeResponse 변환 (Admin Dialog가 요구하는 형태) */
function toNodeResponse(flowNode: FlowNode): NodeResponse {
  return {
    id: flowNode.id,
    labels: [flowNode.data.nodeLabel],
    properties: { ...flowNode.data.properties, name: flowNode.data.name },
  };
}

export function NodeDetailPanel({ className }: NodeDetailPanelProps) {
  const { selectedNodeId, nodes, selectNode, updateNodeData, removeNode } =
    useGraphStore();

  const [editingNode, setEditingNode] = useState<NodeResponse | null>(null);
  const [deletingNode, setDeletingNode] = useState<NodeResponse | null>(null);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  const handleEditSuccess = useCallback(
    (formProperties: Record<string, unknown>) => {
      if (!editingNode) return;
      // Merge form data with original properties to preserve types for unchanged values.
      // EditNodeForm converts all values to strings — so if a value didn't change
      // (string representation matches), keep the original typed value.
      const original = editingNode.properties;
      const merged: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(formProperties)) {
        if (v === null) continue; // deleted property
        if (k in original && String(original[k] ?? '') === String(v)) {
          merged[k] = original[k]; // unchanged — preserve original type
        } else {
          merged[k] = v; // changed — use form value (string)
        }
      }
      updateNodeData(editingNode.id, merged);
    },
    [editingNode, updateNodeData]
  );

  const handleDeleteSuccess = useCallback(() => {
    if (!deletingNode) return;
    removeNode(deletingNode.id);
  }, [deletingNode, removeNode]);

  if (!selectedNode) {
    return null;
  }

  const { data } = selectedNode;

  return (
    <>
      <div
        className={cn(
          'absolute right-4 top-4 z-10 w-72 rounded-lg border bg-background shadow-lg',
          className
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h3 className="font-semibold">Node Details</h3>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              title="Edit node"
              onClick={() => setEditingNode(toNodeResponse(selectedNode))}
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-red-600 hover:text-red-700"
              title="Delete node"
              onClick={() => setDeletingNode(toNodeResponse(selectedNode))}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => selectNode(null)}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Content */}
        <ScrollArea className="max-h-80">
          <div className="space-y-4 p-4">
            {/* Basic Info */}
            <div>
              <h4 className="text-xs font-medium uppercase text-muted-foreground">
                Basic Info
              </h4>
              <dl className="mt-2 space-y-1">
                <div className="flex justify-between">
                  <dt className="text-sm text-muted-foreground">Name</dt>
                  <dd className="text-sm font-medium">{data.name}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm text-muted-foreground">Label</dt>
                  <dd className="text-sm font-medium">{data.nodeLabel}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm text-muted-foreground">Role</dt>
                  <dd className="text-sm font-medium capitalize">{data.role}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm text-muted-foreground">Depth</dt>
                  <dd className="text-sm font-medium">{data.depth}</dd>
                </div>
              </dl>
            </div>

            {/* Properties */}
            {Object.keys(data.properties).length > 0 && (
              <div>
                <h4 className="text-xs font-medium uppercase text-muted-foreground">
                  Properties
                </h4>
                <dl className="mt-2 space-y-1">
                  {Object.entries(data.properties).map(([key, value]) => (
                    <div key={key} className="flex justify-between gap-2">
                      <dt className="truncate text-sm text-muted-foreground">
                        {key}
                      </dt>
                      <dd className="truncate text-sm font-medium">
                        {formatValue(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Edit / Delete Dialogs */}
      <EditNodeDialog
        node={editingNode}
        onOpenChange={(open) => !open && setEditingNode(null)}
        onSuccess={handleEditSuccess}
      />
      <DeleteNodeDialog
        node={deletingNode}
        onOpenChange={(open) => !open && setDeletingNode(null)}
        onSuccess={handleDeleteSuccess}
      />
    </>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export default NodeDetailPanel;
