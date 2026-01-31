import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useOntologyStats } from '@/api/hooks/admin/useOntologyAdmin';
import { Clock, CheckCircle2, XCircle, Zap, Loader2 } from 'lucide-react';

export function OntologyStats() {
  const { data: stats, isLoading } = useOntologyStats();

  if (isLoading || !stats) {
    return (
      <div className="grid gap-4 md:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardContent className="flex items-center justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const statCards = [
    {
      title: 'Pending',
      value: stats.pending_count,
      icon: Clock,
      color: 'text-yellow-600',
      bg: 'bg-yellow-50',
    },
    {
      title: 'Approved',
      value: stats.approved_count,
      icon: CheckCircle2,
      color: 'text-green-600',
      bg: 'bg-green-50',
    },
    {
      title: 'Auto-Approved',
      value: stats.auto_approved_count,
      icon: Zap,
      color: 'text-blue-600',
      bg: 'bg-blue-50',
    },
    {
      title: 'Rejected',
      value: stats.rejected_count,
      icon: XCircle,
      color: 'text-red-600',
      bg: 'bg-red-50',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        {statCards.map((stat) => (
          <Card key={stat.title}>
            <CardContent className="flex items-center gap-4 py-4">
              <div className={`rounded-lg p-3 ${stat.bg}`}>
                <stat.icon className={`h-5 w-5 ${stat.color}`} />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">{stat.title}</p>
                <p className="text-2xl font-bold">{stat.value}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Category Distribution & Top Terms */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Category Distribution */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Category Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(stats.category_distribution).length === 0 ? (
              <p className="text-sm text-muted-foreground">No data available</p>
            ) : (
              <div className="space-y-3">
                {Object.entries(stats.category_distribution)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 5)
                  .map(([category, count]) => (
                    <div key={category} className="flex items-center justify-between">
                      <span className="text-sm font-medium">{category}</span>
                      <span className="text-sm text-muted-foreground tabular-nums">{count}</span>
                    </div>
                  ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top Unresolved Terms */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Top Unresolved Terms</CardTitle>
          </CardHeader>
          <CardContent>
            {stats.top_unresolved_terms.length === 0 ? (
              <p className="text-sm text-muted-foreground">No unresolved terms</p>
            ) : (
              <div className="space-y-3">
                {stats.top_unresolved_terms.slice(0, 5).map((term) => (
                  <div key={term.term} className="flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">{term.term}</span>
                      <span className="text-xs text-muted-foreground">{term.category}</span>
                    </div>
                    <div className="text-right">
                      <span className="text-sm tabular-nums">{term.frequency}x</span>
                      <span className="text-xs text-muted-foreground ml-2">
                        {(term.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
