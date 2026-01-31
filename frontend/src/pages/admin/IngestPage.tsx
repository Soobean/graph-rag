import { IngestForm } from '@/components/admin/ingest/IngestForm';
import { JobList } from '@/components/admin/ingest/JobList';

export function IngestPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Data Ingestion</h1>
        <p className="text-muted-foreground">Import data from CSV or Excel files into the graph database</p>
      </div>

      <IngestForm />
      <JobList />
    </div>
  );
}
