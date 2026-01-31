import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useIngestJobs } from '@/api/hooks/admin/useIngest';
import { Loader2, CheckCircle2, XCircle, Clock, Play } from 'lucide-react';
import type { IngestJob } from '@/types/admin';

export function JobList() {
  const { data: jobs, isLoading } = useIngestJobs();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!jobs || jobs.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <Clock className="h-12 w-12 mb-4" />
          <p>No ingestion jobs yet</p>
          <p className="text-sm">Start a new ingestion above</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-lg">Recent Jobs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {jobs.map((job) => (
          <JobCard key={job.job_id} job={job} />
        ))}
      </CardContent>
    </Card>
  );
}

function JobCard({ job }: { job: IngestJob }) {
  const getStatusIcon = () => {
    switch (job.status) {
      case 'completed':
        return <CheckCircle2 className="h-5 w-5 text-green-600" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-600" />;
      case 'running':
        return <Play className="h-5 w-5 text-blue-600" />;
      default:
        return <Clock className="h-5 w-5 text-yellow-600" />;
    }
  };

  const getStatusBadge = () => {
    switch (job.status) {
      case 'completed':
        return <Badge variant="success">Completed</Badge>;
      case 'failed':
        return <Badge variant="destructive">Failed</Badge>;
      case 'running':
        return <Badge variant="default">Running</Badge>;
      default:
        return <Badge variant="warning">Pending</Badge>;
    }
  };

  return (
    <div className="rounded-lg border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {getStatusIcon()}
          <div>
            <p className="font-mono text-sm">{job.job_id}</p>
            {getStatusBadge()}
          </div>
        </div>
        {job.stats.duration_seconds > 0 && (
          <span className="text-sm text-muted-foreground">
            {job.stats.duration_seconds.toFixed(2)}s
          </span>
        )}
      </div>

      {/* Progress Bar (for running jobs) */}
      {(job.status === 'pending' || job.status === 'running') && (
        <div className="space-y-1">
          <Progress value={job.progress * 100} />
          <p className="text-xs text-muted-foreground text-right">
            {(job.progress * 100).toFixed(0)}%
          </p>
        </div>
      )}

      {/* Stats (for completed jobs) */}
      {job.status === 'completed' && (
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <p className="text-lg font-bold">{job.stats.total_nodes}</p>
            <p className="text-xs text-muted-foreground">Nodes</p>
          </div>
          <div>
            <p className="text-lg font-bold">{job.stats.total_edges}</p>
            <p className="text-xs text-muted-foreground">Edges</p>
          </div>
          <div>
            <p className="text-lg font-bold">{job.stats.failed_documents}</p>
            <p className="text-xs text-muted-foreground">Failed</p>
          </div>
        </div>
      )}

      {/* Error (for failed jobs) */}
      {job.status === 'failed' && job.error && (
        <div className="rounded-md bg-red-50 p-2 text-sm text-red-700">{job.error}</div>
      )}
    </div>
  );
}
