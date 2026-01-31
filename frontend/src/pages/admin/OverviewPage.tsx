import { SystemStatusCard } from '@/components/admin/overview/SystemStatusCard';
import { GraphStatsCard } from '@/components/admin/overview/GraphStatsCard';

export function OverviewPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">System Overview</h1>
        <p className="text-muted-foreground">Monitor system health and graph statistics</p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <SystemStatusCard />
        <GraphStatsCard />
      </div>
    </div>
  );
}
