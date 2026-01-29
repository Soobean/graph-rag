import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useGraphStore } from '@/stores';
import { cn } from '@/lib/utils';

interface NodeDetailPanelProps {
  className?: string;
}

export function NodeDetailPanel({ className }: NodeDetailPanelProps) {
  const { selectedNodeId, nodes, selectNode } = useGraphStore();

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  if (!selectedNode) {
    return null;
  }

  const { data } = selectedNode;

  return (
    <div
      className={cn(
        'absolute right-4 top-4 z-10 w-72 rounded-lg border bg-background shadow-lg',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h3 className="font-semibold">Node Details</h3>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => selectNode(null)}
        >
          <X className="h-4 w-4" />
        </Button>
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
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export default NodeDetailPanel;
