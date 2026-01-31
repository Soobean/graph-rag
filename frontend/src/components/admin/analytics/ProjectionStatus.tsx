import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useProjectionStatus, useCreateProjection, useDeleteProjection } from '@/api/hooks/admin/useAnalytics';
import { Database, Loader2, Plus, Trash2 } from 'lucide-react';

export function ProjectionStatus() {
  const { data: status, isLoading } = useProjectionStatus();
  const createProjection = useCreateProjection();
  const deleteProjection = useDeleteProjection();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Graph Projection</CardTitle>
          {status?.exists ? (
            <Badge variant="success">Active</Badge>
          ) : (
            <Badge variant="secondary">Not Created</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {status?.exists ? (
          <>
            <div className="grid grid-cols-2 gap-4 text-center">
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-2xl font-bold">{status.node_count?.toLocaleString() || 0}</p>
                <p className="text-xs text-muted-foreground">Nodes</p>
              </div>
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-2xl font-bold">{status.relationship_count?.toLocaleString() || 0}</p>
                <p className="text-xs text-muted-foreground">Relationships</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">{status.name}</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="w-full text-destructive hover:text-destructive"
              onClick={() => deleteProjection.mutate()}
              disabled={deleteProjection.isPending}
            >
              {deleteProjection.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-4 w-4" />
              )}
              Delete Projection
            </Button>
          </>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Create a graph projection to enable community detection, similarity search, and team recommendations.
            </p>
            <Button
              size="sm"
              className="w-full"
              onClick={() => createProjection.mutate(2)}
              disabled={createProjection.isPending}
            >
              {createProjection.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-2 h-4 w-4" />
              )}
              Create Projection
            </Button>
          </>
        )}

        {createProjection.error && (
          <div className="rounded-md bg-red-50 p-2 text-sm text-red-700" role="alert">
            {createProjection.error instanceof Error
              ? createProjection.error.message
              : 'Failed to create projection'}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
