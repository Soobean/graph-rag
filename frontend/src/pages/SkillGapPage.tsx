import { Link } from 'react-router-dom';
import { ArrowLeft, Target } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SkillGapAnalysis } from '@/components/admin/analytics/SkillGapAnalysis';

export function SkillGapPage() {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
        <div className="flex items-center gap-3">
          <Link to="/">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="mr-1 h-4 w-4" />
              Back
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            <h1 className="text-xl font-bold">Skill Gap Analysis</h1>
          </div>
        </div>
      </header>

      {/* Content — full width for matrix */}
      <main className="flex-1 overflow-y-auto px-6 py-5">
        <SkillGapAnalysis />
      </main>
    </div>
  );
}
