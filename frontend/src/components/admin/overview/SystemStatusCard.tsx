import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useHealth } from '@/api/hooks';
import { Activity, AlertCircle, Database, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

export function SystemStatusCard() {
  const { data: health, isLoading, isError } = useHealth();

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">System Status</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Checking status...</span>
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span className="font-medium">API Disconnected</span>
          </div>
        ) : (
          <>
            {/* API Status */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">API Status</span>
              </div>
              <StatusBadge
                status={health?.status === 'healthy' ? 'success' : 'warning'}
                label={health?.status === 'healthy' ? 'Healthy' : 'Degraded'}
              />
            </div>

            {/* Neo4j Connection */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Database className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">Neo4j Connection</span>
              </div>
              <StatusBadge
                status={health?.neo4j_connected ? 'success' : 'error'}
                label={health?.neo4j_connected ? 'Connected' : 'Disconnected'}
              />
            </div>

            {/* Version */}
            {health?.version && (
              <div className="flex items-center justify-between pt-2 border-t">
                <span className="text-sm text-muted-foreground">Version</span>
                <span className="text-sm font-mono">{health.version}</span>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

interface StatusBadgeProps {
  status: 'success' | 'warning' | 'error';
  label: string;
}

function StatusBadge({ status, label }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-1 text-xs font-medium',
        status === 'success' && 'bg-green-100 text-green-800',
        status === 'warning' && 'bg-yellow-100 text-yellow-800',
        status === 'error' && 'bg-red-100 text-red-800'
      )}
    >
      <span
        className={cn(
          'mr-1.5 h-1.5 w-1.5 rounded-full',
          status === 'success' && 'bg-green-500',
          status === 'warning' && 'bg-yellow-500',
          status === 'error' && 'bg-red-500'
        )}
      />
      {label}
    </span>
  );
}
