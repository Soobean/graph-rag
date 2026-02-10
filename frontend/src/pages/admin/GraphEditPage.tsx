import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Plus, Link } from 'lucide-react';
import { NodeSearchFilters } from '@/components/admin/graph-edit/NodeSearchFilters';
import { NodeListTable } from '@/components/admin/graph-edit/NodeListTable';
import { DeleteNodeDialog } from '@/components/admin/graph-edit/DeleteNodeDialog';
import { EditNodeDialog } from '@/components/admin/graph-edit/EditNodeDialog';
import { CreateNodeDialog } from '@/components/admin/graph-edit/CreateNodeDialog';
import { CreateEdgeDialog } from '@/components/admin/graph-edit/CreateEdgeDialog';
import { useNodeSearch } from '@/api/hooks/admin/useGraphEdit';
import type { NodeResponse, NodeSearchParams } from '@/types/graphEdit';

export function GraphEditPage() {
  const [filters, setFilters] = useState<NodeSearchParams>({
    limit: 50,
  });
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createEdgeDialogOpen, setCreateEdgeDialogOpen] = useState(false);
  const [editingNode, setEditingNode] = useState<NodeResponse | null>(null);
  const [deletingNode, setDeletingNode] = useState<NodeResponse | null>(null);
  const [impactNode, setImpactNode] = useState<NodeResponse | null>(null);

  const { data, isLoading } = useNodeSearch(filters);

  const handleEdit = (node: NodeResponse) => {
    setEditingNode(node);
  };

  const handleDelete = (node: NodeResponse) => {
    setImpactNode(null);
    setDeletingNode(node);
  };

  const handleViewImpact = (node: NodeResponse) => {
    setDeletingNode(null);
    setImpactNode(node);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Graph Edit</h1>
        <p className="text-muted-foreground">
          Create, edit, and delete nodes and edges in the knowledge graph
        </p>
      </div>

      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Nodes</CardTitle>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCreateEdgeDialogOpen(true)}
              >
                <Link className="mr-2 h-4 w-4" />
                Create Edge
              </Button>
              <Button size="sm" onClick={() => setCreateDialogOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Create Node
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <NodeSearchFilters filters={filters} onFiltersChange={setFilters} />
          <NodeListTable
            nodes={data?.nodes || []}
            isLoading={isLoading}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onViewImpact={handleViewImpact}
          />
          {data && (
            <p className="text-sm text-muted-foreground">
              {data.count} node{data.count !== 1 ? 's' : ''} found
            </p>
          )}
        </CardContent>
      </Card>

      {/* Dialogs */}
      <CreateNodeDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />

      <CreateEdgeDialog
        open={createEdgeDialogOpen}
        onOpenChange={setCreateEdgeDialogOpen}
      />

      <EditNodeDialog
        node={editingNode}
        onOpenChange={(open) => {
          if (!open) setEditingNode(null);
        }}
      />

      <DeleteNodeDialog
        key={deletingNode?.id ?? impactNode?.id}
        node={deletingNode ?? impactNode}
        onOpenChange={(open) => {
          if (!open) {
            setDeletingNode(null);
            setImpactNode(null);
          }
        }}
        previewOnly={!!impactNode && !deletingNode}
      />
    </div>
  );
}
