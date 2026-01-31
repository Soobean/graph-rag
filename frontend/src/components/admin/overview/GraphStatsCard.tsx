import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useSchema } from '@/api/hooks/admin';
import { Network, GitBranch, Loader2, AlertCircle } from 'lucide-react';

export function GraphStatsCard() {
  const { data: schema, isLoading, isError } = useSchema();

  const nodeCount = schema?.nodes?.length || 0;
  const edgeCount = schema?.edges?.length || 0;

  const nodeLabels = schema?.nodes?.map((n) => n.name) || [];
  const relationshipTypes = [...new Set(schema?.edges?.map((e) => e.label) || [])];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">Graph Schema</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Loading schema...</span>
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load schema</span>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Stats */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Network className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">Node Types</span>
                </div>
                <p className="text-2xl font-bold">{nodeCount}</p>
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <GitBranch className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">Relationship Types</span>
                </div>
                <p className="text-2xl font-bold">{edgeCount}</p>
              </div>
            </div>

            {/* Labels */}
            {nodeLabels.length > 0 && (
              <div className="space-y-2 pt-2 border-t">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Node Labels
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {nodeLabels.map((label) => (
                    <span
                      key={label}
                      className="inline-flex items-center rounded-md bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 ring-1 ring-inset ring-blue-700/10"
                    >
                      {label}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Relationships */}
            {relationshipTypes.length > 0 && (
              <div className="space-y-2 pt-2 border-t">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Relationship Types
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {relationshipTypes.map((rel) => (
                    <span
                      key={rel}
                      className="inline-flex items-center rounded-md bg-purple-50 px-2 py-1 text-xs font-medium text-purple-700 ring-1 ring-inset ring-purple-700/10"
                    >
                      {rel}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
