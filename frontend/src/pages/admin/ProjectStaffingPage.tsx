import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ProjectStaffing } from '@/components/admin/staffing/ProjectStaffing';

export function ProjectStaffingPage() {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-3">
          <Link to="/">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="mr-1 h-4 w-4" />
              Back
            </Button>
          </Link>
          <h1 className="text-xl font-bold">Project Staffing</h1>
          <span className="text-sm text-muted-foreground">비용 기반 프로젝트 인력 배치</span>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-7xl">
          <ProjectStaffing />
        </div>
      </main>
    </div>
  );
}
