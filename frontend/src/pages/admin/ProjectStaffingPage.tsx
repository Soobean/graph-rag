import { ProjectStaffing } from '@/components/admin/staffing/ProjectStaffing';

export function ProjectStaffingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Project Staffing</h1>
        <p className="text-muted-foreground">
          비용 기반 프로젝트 인력 배치
        </p>
      </div>
      <ProjectStaffing />
    </div>
  );
}
