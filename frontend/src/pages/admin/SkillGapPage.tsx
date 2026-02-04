import { SkillGapAnalysis } from '@/components/admin/analytics/SkillGapAnalysis';

export function SkillGapPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Skill Gap Analysis</h1>
        <p className="text-muted-foreground">
          Analyze team skill gaps and get recommendations for filling them
        </p>
      </div>

      <SkillGapAnalysis />
    </div>
  );
}
