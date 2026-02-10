import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useAnalyzeSkillGap, useRecommendGapSolution } from '@/api/hooks/admin';
import { cn } from '@/lib/utils';
import {
  Users,
  Loader2,
  Search,
  X,
  Check,
  Minus,
  CircleAlert,
  UserPlus,
  AlertTriangle,
  GitMerge,
  Lightbulb,
  Target,
  ShieldAlert,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react';
import type {
  SkillGapAnalyzeResponse,
  SkillRecommendResponse,
  SkillCoverage,
  CoverageStatus,
  RecommendedEmployee,
  Insight,
  InsightType,
  InsightSeverity,
} from '@/types/admin';

// ============================================
// Constants
// ============================================

const STATUS_BADGE_VARIANT: Record<CoverageStatus, 'success' | 'warning' | 'destructive'> = {
  covered: 'success',
  partial: 'warning',
  gap: 'destructive',
};

const STATUS_LABEL: Record<CoverageStatus, string> = {
  covered: 'Covered',
  partial: 'Partial',
  gap: 'Gap',
};

const INSIGHT_CONFIG: Record<InsightType, { icon: LucideIcon; iconColor: string }> = {
  rare_skill: { icon: AlertTriangle, iconColor: 'text-amber-500' },
  synergy: { icon: Users, iconColor: 'text-blue-500' },
  bridge: { icon: GitMerge, iconColor: 'text-purple-500' },
  alternative: { icon: Lightbulb, iconColor: 'text-green-500' },
};

const SEVERITY_STYLES: Record<InsightSeverity, string> = {
  warning: 'bg-amber-50 border-amber-200',
  info: 'bg-blue-50 border-blue-200',
  success: 'bg-green-50 border-green-200',
};

const CATEGORY_COLOR_MAP: Record<string, string> = {
  blue: 'bg-blue-500',
  green: 'bg-green-500',
  purple: 'bg-purple-500',
  orange: 'bg-orange-500',
  red: 'bg-red-500',
  yellow: 'bg-yellow-500',
  indigo: 'bg-indigo-500',
  pink: 'bg-pink-500',
  teal: 'bg-teal-500',
  cyan: 'bg-cyan-500',
};

type CellStatus = 'exact' | 'similar' | 'gap';

interface MatrixCell {
  status: CellStatus;
  possessedSkill?: string;
}

// ============================================
// Sub-components (unchanged)
// ============================================

function getAvailabilityInfo(projectCount: number) {
  if (projectCount <= 1) {
    return { label: 'Available', color: 'text-green-600', dot: 'bg-green-500' };
  }
  if (projectCount <= 3) {
    return { label: `${projectCount} projects`, color: 'text-yellow-600', dot: 'bg-yellow-500' };
  }
  return { label: `${projectCount} projects`, color: 'text-red-600', dot: 'bg-red-500' };
}

function CandidateRecommendations({
  candidates,
  externalSearchQuery,
}: {
  candidates: RecommendedEmployee[];
  externalSearchQuery: string;
}) {
  if (candidates.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">Recommended Candidates</p>
        <p className="text-sm text-muted-foreground">No internal candidates found.</p>
        {externalSearchQuery && (
          <p className="text-xs text-muted-foreground">
            External search: {externalSearchQuery}
          </p>
        )}
      </div>
    );
  }

  const available = candidates.filter((c) => c.current_projects <= 1);
  const busy = candidates.filter((c) => c.current_projects > 1);

  return (
    <div className="space-y-3">
      {available.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">
            Available Candidates ({available.length})
          </p>
          {available.map((candidate) => (
            <CandidateCard key={candidate.name} candidate={candidate} />
          ))}
        </div>
      )}
      {busy.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">
            {available.length > 0 ? 'Alternative ' : ''}Candidates - Busy ({busy.length})
          </p>
          {busy.map((candidate) => (
            <CandidateCard key={candidate.name} candidate={candidate} />
          ))}
        </div>
      )}
      {externalSearchQuery && (
        <p className="text-xs text-muted-foreground">
          External search: {externalSearchQuery}
        </p>
      )}
    </div>
  );
}

function CandidateCard({ candidate }: { candidate: RecommendedEmployee }) {
  const availability = getAvailabilityInfo(candidate.current_projects);

  return (
    <div className="flex items-center gap-3 rounded-md border bg-background p-2">
      <UserPlus className="h-4 w-4 text-muted-foreground" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{candidate.name}</p>
          <span className={`flex items-center gap-1 text-xs ${availability.color}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${availability.dot}`} />
            {availability.label}
          </span>
        </div>
        {candidate.department && (
          <p className="text-xs text-muted-foreground">{candidate.department}</p>
        )}
        <p className="text-xs text-muted-foreground">{candidate.reason}</p>
      </div>
    </div>
  );
}

function InsightCard({ insight }: { insight: Insight }) {
  const config = INSIGHT_CONFIG[insight.type];
  const Icon = config.icon;

  return (
    <div className={`rounded-lg border p-3 ${SEVERITY_STYLES[insight.severity]}`}>
      <div className="flex items-start gap-3">
        <Icon className={`h-5 w-5 mt-0.5 flex-shrink-0 ${config.iconColor}`} />
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm">{insight.title}</p>
          <p className="text-sm text-muted-foreground mt-1">{insight.description}</p>
          {insight.related_people.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {insight.related_people.map((name) => (
                <Badge key={name} variant="outline" className="text-xs">
                  {name}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================
// Matrix Cell
// ============================================

function MatrixCellView({
  cell,
  isHighlighted,
  onClick,
}: {
  cell: MatrixCell;
  isHighlighted: boolean;
  onClick?: () => void;
}) {
  const isClickable = cell.status !== 'exact' && !!onClick;

  return (
    <button
      type="button"
      disabled={!isClickable}
      onClick={isClickable ? onClick : undefined}
      title={
        cell.status === 'exact'
          ? 'Has this skill'
          : cell.status === 'similar'
            ? `Has similar: ${cell.possessedSkill}`
            : 'Skill gap — click for recommendations'
      }
      className={cn(
        'flex h-9 w-9 items-center justify-center rounded-md transition-all',
        cell.status === 'exact' && 'bg-emerald-500/20 text-emerald-600',
        cell.status === 'similar' && 'bg-amber-400/20 text-amber-600',
        cell.status === 'gap' && 'bg-red-500/10 text-red-400 border border-dashed border-red-300',
        isHighlighted && 'ring-2 ring-primary ring-offset-1',
        isClickable && 'cursor-pointer hover:scale-110',
      )}
    >
      {cell.status === 'exact' && <Check className="h-4 w-4" />}
      {cell.status === 'similar' && <Minus className="h-4 w-4" />}
      {cell.status === 'gap' && <CircleAlert className="h-3.5 w-3.5" />}
    </button>
  );
}

// ============================================
// Skill Matrix Grid
// ============================================

function SkillMatrix({
  result,
  expandedSkill,
  onSkillClick,
}: {
  result: SkillGapAnalyzeResponse;
  expandedSkill: string | null;
  onSkillClick: (skill: SkillCoverage) => void;
}) {
  // Build matrix: rows = team members, columns = skills
  const matrix: { member: string; cells: MatrixCell[] }[] = result.team_members.map(
    (member) => ({
      member,
      cells: result.skill_details.map((skill) => {
        if (skill.exact_matches.includes(member)) {
          return { status: 'exact' as const };
        }
        const similar = skill.similar_matches.find((m) => m.employee_name === member);
        if (similar) {
          return { status: 'similar' as const, possessedSkill: similar.possessed_skill };
        }
        return { status: 'gap' as const };
      }),
    }),
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-1">
        <thead>
          <tr>
            {/* Corner cell */}
            <th className="sticky left-0 z-10 bg-background" />
            {/* Skill column headers */}
            {result.skill_details.map((skill) => (
              <th key={skill.skill} className="pb-2 px-1">
                <button
                  type="button"
                  onClick={() => onSkillClick(skill)}
                  className={cn(
                    'flex flex-col items-center gap-1 text-xs font-medium transition-colors',
                    expandedSkill === skill.skill
                      ? 'text-primary'
                      : 'text-muted-foreground hover:text-foreground',
                    skill.status !== 'covered' && 'cursor-pointer',
                  )}
                >
                  <span className="max-w-[80px] truncate">{skill.skill}</span>
                  <Badge
                    variant={STATUS_BADGE_VARIANT[skill.status]}
                    className="text-[10px] px-1.5 py-0"
                  >
                    {STATUS_LABEL[skill.status]}
                  </Badge>
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row) => (
            <tr key={row.member}>
              {/* Member name */}
              <td className="sticky left-0 z-10 bg-background pr-3 text-sm font-medium whitespace-nowrap">
                {row.member}
              </td>
              {/* Cells */}
              {row.cells.map((cell, colIdx) => {
                const skill = result.skill_details[colIdx];
                return (
                  <td key={skill.skill} className="text-center">
                    <MatrixCellView
                      cell={cell}
                      isHighlighted={expandedSkill === skill.skill}
                      onClick={
                        skill.status !== 'covered'
                          ? () => onSkillClick(skill)
                          : undefined
                      }
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ============================================
// Summary Stats
// ============================================

function SummaryStats({ result }: { result: SkillGapAnalyzeResponse }) {
  const totalSkills = result.skill_details.length;
  const coveredCount = result.skill_details.filter((s) => s.status === 'covered').length;
  const partialCount = result.skill_details.filter((s) => s.status === 'partial').length;
  const gapCount = result.gaps.length;
  const coveragePercent = totalSkills > 0 ? Math.round(((coveredCount + partialCount * 0.5) / totalSkills) * 100) : 0;

  return (
    <div className="grid grid-cols-4 gap-3">
      <Card className="border-l-4 border-l-emerald-500">
        <CardContent className="p-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            <span className="text-xs text-muted-foreground">Coverage</span>
          </div>
          <p className="mt-1 text-2xl font-bold">{coveragePercent}%</p>
        </CardContent>
      </Card>
      <Card className="border-l-4 border-l-blue-500">
        <CardContent className="p-4">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-blue-500" />
            <span className="text-xs text-muted-foreground">Team</span>
          </div>
          <p className="mt-1 text-2xl font-bold">{result.team_members.length}</p>
        </CardContent>
      </Card>
      <Card className="border-l-4 border-l-amber-500">
        <CardContent className="p-4">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-amber-500" />
            <span className="text-xs text-muted-foreground">Skills</span>
          </div>
          <p className="mt-1 text-2xl font-bold">
            {coveredCount}<span className="text-sm font-normal text-muted-foreground">/{totalSkills}</span>
          </p>
        </CardContent>
      </Card>
      <Card className="border-l-4 border-l-red-500">
        <CardContent className="p-4">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-red-500" />
            <span className="text-xs text-muted-foreground">Gaps</span>
          </div>
          <p className="mt-1 text-2xl font-bold">{gapCount}</p>
        </CardContent>
      </Card>
    </div>
  );
}

// ============================================
// Main Component
// ============================================

export function SkillGapAnalysis() {
  // Input state
  const [skillInput, setSkillInput] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [teamMode, setTeamMode] = useState<'members' | 'project'>('members');
  const [memberInput, setMemberInput] = useState('');
  const [members, setMembers] = useState<string[]>([]);
  const [projectId, setProjectId] = useState('');

  // Results state
  const [result, setResult] = useState<SkillGapAnalyzeResponse | null>(null);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Record<string, SkillRecommendResponse>>({});

  const analyzeGap = useAnalyzeSkillGap();
  const recommendSolution = useRecommendGapSolution();

  const handleAddSkill = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === 'Enter' && skillInput.trim()) {
      e.preventDefault();
      if (!skills.includes(skillInput.trim())) {
        setSkills([...skills, skillInput.trim()]);
      }
      setSkillInput('');
    }
  };

  const handleRemoveSkill = (skill: string) => {
    setSkills(skills.filter((s) => s !== skill));
  };

  const handleAddMember = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === 'Enter' && memberInput.trim()) {
      e.preventDefault();
      if (!members.includes(memberInput.trim())) {
        setMembers([...members, memberInput.trim()]);
      }
      setMemberInput('');
    }
  };

  const handleRemoveMember = (member: string) => {
    setMembers(members.filter((m) => m !== member));
  };

  const canAnalyze =
    skills.length > 0 &&
    ((teamMode === 'members' && members.length > 0) || (teamMode === 'project' && projectId.trim()));

  const handleAnalyze = () => {
    if (!canAnalyze) return;

    const request =
      teamMode === 'members'
        ? { required_skills: skills, team_members: members }
        : { required_skills: skills, project_id: projectId.trim() };

    analyzeGap.mutate(request, {
      onSuccess: (data) => {
        setResult(data);
        setExpandedSkill(null);
        setRecommendations({});
      },
    });
  };

  const handleSkillClick = (skillDetail: SkillCoverage) => {
    if (skillDetail.status === 'covered') return;

    const skillName = skillDetail.skill;
    if (expandedSkill === skillName) {
      setExpandedSkill(null);
      return;
    }

    setExpandedSkill(skillName);

    if (!recommendations[skillName]) {
      recommendSolution.mutate(
        {
          skill: skillName,
          exclude_members: result?.team_members ?? [],
          limit: 5,
        },
        {
          onSuccess: (data) => {
            setRecommendations((prev) => ({ ...prev, [skillName]: data }));
          },
        }
      );
    }
  };

  // Find expanded skill detail
  const expandedSkillDetail = expandedSkill
    ? result?.skill_details.find((s) => s.skill === expandedSkill)
    : null;

  return (
    <div className="space-y-6">
      {/* ── Form Section ── */}
      <Card>
        <CardContent className="p-5">
          <div className="grid gap-5 md:grid-cols-2">
            {/* Left: Skills */}
            <div className="space-y-2">
              <label htmlFor="required-skills" className="text-sm font-medium">
                Required Skills
              </label>
              <Input
                id="required-skills"
                value={skillInput}
                onChange={(e) => setSkillInput(e.target.value)}
                onKeyDown={handleAddSkill}
                placeholder="Type a skill and press Enter..."
              />
              {skills.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {skills.map((skill) => (
                    <Badge key={skill} variant="secondary" className="gap-1">
                      {skill}
                      <button
                        type="button"
                        onClick={() => handleRemoveSkill(skill)}
                        className="ml-1 rounded-full hover:bg-muted"
                        aria-label={`Remove ${skill}`}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            {/* Right: Team */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium">Team Source</label>
                <div className="flex gap-1">
                  <Button
                    variant={teamMode === 'members' ? 'default' : 'outline'}
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => setTeamMode('members')}
                  >
                    <Users className="mr-1 h-3 w-3" />
                    Members
                  </Button>
                  <Button
                    variant={teamMode === 'project' ? 'default' : 'outline'}
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => setTeamMode('project')}
                  >
                    <Search className="mr-1 h-3 w-3" />
                    Project
                  </Button>
                </div>
              </div>

              {teamMode === 'members' ? (
                <>
                  <Input
                    id="team-members"
                    value={memberInput}
                    onChange={(e) => setMemberInput(e.target.value)}
                    onKeyDown={handleAddMember}
                    placeholder="Type a member name and press Enter..."
                  />
                  {members.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {members.map((member) => (
                        <Badge key={member} variant="outline" className="gap-1">
                          {member}
                          <button
                            type="button"
                            onClick={() => handleRemoveMember(member)}
                            className="ml-1 rounded-full hover:bg-muted"
                            aria-label={`Remove ${member}`}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <Input
                  id="project-id"
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  placeholder="Enter project ID..."
                />
              )}
            </div>
          </div>

          {/* Analyze button */}
          <div className="mt-4 flex items-center gap-3">
            <Button onClick={handleAnalyze} disabled={analyzeGap.isPending || !canAnalyze}>
              {analyzeGap.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Search className="mr-2 h-4 w-4" />
              )}
              Analyze
            </Button>
            {analyzeGap.error && (
              <span className="text-sm text-red-600">
                {analyzeGap.error instanceof Error ? analyzeGap.error.message : 'An error occurred'}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── Results ── */}
      {result ? (
        <>
          {/* Summary Stats */}
          <SummaryStats result={result} />

          {/* Matrix + Detail — side by side on large screens */}
          <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
            {/* Skill Matrix */}
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Skill Matrix</CardTitle>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                      <span className="inline-flex h-4 w-4 items-center justify-center rounded bg-emerald-500/20">
                        <Check className="h-3 w-3 text-emerald-600" />
                      </span>
                      Exact
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="inline-flex h-4 w-4 items-center justify-center rounded bg-amber-400/20">
                        <Minus className="h-3 w-3 text-amber-600" />
                      </span>
                      Similar
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="inline-flex h-4 w-4 items-center justify-center rounded border border-dashed border-red-300 bg-red-500/10">
                        <CircleAlert className="h-3 w-3 text-red-400" />
                      </span>
                      Gap
                    </span>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <SkillMatrix
                  result={result}
                  expandedSkill={expandedSkill}
                  onSkillClick={handleSkillClick}
                />
              </CardContent>
            </Card>

            {/* Skill Detail Panel (right sidebar) */}
            <div className="space-y-4">
              {expandedSkillDetail ? (
                <Card className="border-primary/30">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">{expandedSkillDetail.skill}</CardTitle>
                      <Badge variant={STATUS_BADGE_VARIANT[expandedSkillDetail.status]}>
                        {STATUS_LABEL[expandedSkillDetail.status]}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <p className="text-sm text-muted-foreground">{expandedSkillDetail.explanation}</p>

                    {/* Current Coverage */}
                    {(expandedSkillDetail.exact_matches.length > 0 || expandedSkillDetail.similar_matches.length > 0) && (
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-muted-foreground">Current Team Coverage</p>
                        {expandedSkillDetail.exact_matches.map((name, idx) => (
                          <div key={`exact-${idx}`} className="flex items-center gap-2 text-sm">
                            <Badge variant="success" className="text-xs">Exact</Badge>
                            <span>{name}</span>
                          </div>
                        ))}
                        {expandedSkillDetail.similar_matches.map((match, idx) => (
                          <div key={`similar-${idx}`} className="flex items-center gap-2 text-sm">
                            <Badge variant="outline" className="text-xs">Similar</Badge>
                            <span>{match.employee_name}</span>
                            <span className="text-muted-foreground">({match.possessed_skill})</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Recommendations */}
                    {recommendations[expandedSkillDetail.skill] ? (
                      <CandidateRecommendations
                        candidates={recommendations[expandedSkillDetail.skill].internal_candidates}
                        externalSearchQuery={recommendations[expandedSkillDetail.skill].external_search_query}
                      />
                    ) : recommendSolution.isPending ? (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Loading recommendations...
                      </div>
                    ) : recommendSolution.error ? (
                      <p className="text-sm text-red-600">Failed to load recommendations</p>
                    ) : null}
                  </CardContent>
                </Card>
              ) : (
                <Card className="border-dashed">
                  <CardContent className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
                    <CircleAlert className="mb-2 h-8 w-8 opacity-30" />
                    <p className="text-sm">Click a gap or partial skill in the matrix to see details and recommendations</p>
                  </CardContent>
                </Card>
              )}

              {/* Category Coverage */}
              {result.category_summary.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Category Coverage</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {result.category_summary.map((cat) => (
                      <div key={cat.category} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <div className="flex items-center gap-2">
                            <span className={`h-2 w-2 rounded-full ${CATEGORY_COLOR_MAP[cat.color] || 'bg-gray-500'}`} />
                            <span>{cat.category}</span>
                          </div>
                          <span className="text-muted-foreground">
                            {cat.covered_count}/{cat.total_skills} ({(cat.coverage_ratio * 100).toFixed(0)}%)
                          </span>
                        </div>
                        <Progress value={cat.coverage_ratio * 100} className="h-2" />
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>

          {/* Bottom: Insights + Gaps + Recommendations */}
          <div className="grid gap-4 md:grid-cols-2">
            {/* Insights */}
            {result.insights && result.insights.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Insights</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {result.insights.map((insight, idx) => (
                    <InsightCard key={`${insight.type}-${idx}`} insight={insight} />
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Gaps + Recommendations */}
            {(result.gaps.length > 0 || result.recommendations.length > 0) && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Action Items</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {result.gaps.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-sm font-medium">
                        Gap Skills ({result.gaps.length})
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {result.gaps.map((gap) => (
                          <Badge key={gap} variant="destructive">{gap}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {result.recommendations.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-sm font-medium">Recommendations</p>
                      <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                        {result.recommendations.map((rec, idx) => (
                          <li key={idx}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </>
      ) : !analyzeGap.isPending ? (
        /* Empty state */
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <Target className="mb-4 h-12 w-12 text-muted-foreground/30" />
            <h3 className="text-lg font-medium text-muted-foreground">No Analysis Yet</h3>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground/80">
              Enter required skills and team members above, then click Analyze to generate a skill gap matrix
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
