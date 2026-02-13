import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select } from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  useStaffingProjects,
  useStaffingCategories,
  useFindCandidates,
  useGenerateStaffingPlan,
  useAnalyzeBudget,
} from '@/api/hooks/admin';
import { Loader2, Search, ClipboardList, TrendingDown, ChevronRight, ChevronDown } from 'lucide-react';
import type {
  CandidateInfo,
  FindCandidatesResponse,
  StaffingPlanResponse,
  BudgetAnalysisResponse,
  SkillCandidates,
} from '@/types/admin';
import { formatKRW, formatRate } from '@/lib/formatters';

type ImportanceBadgeVariant = 'destructive' | 'warning' | 'secondary';

function importanceBadge(importance: string | null): {
  label: string;
  variant: ImportanceBadgeVariant;
} {
  switch (importance) {
    case '필수':
      return { label: '필수', variant: 'destructive' };
    case '우대':
      return { label: '우대', variant: 'warning' };
    default:
      return { label: importance || '선택', variant: 'secondary' };
  }
}

function proficiencyLabel(level: number): string {
  const labels: Record<number, string> = {
    1: '초급',
    2: '중급',
    3: '고급',
    4: '전문가',
  };
  return labels[level] || `${level}`;
}

// ============================================
// Match Score Helpers
// ============================================

type BadgeVariant = 'success' | 'warning' | 'secondary' | 'destructive';

function matchScoreBadgeVariant(score: number): BadgeVariant {
  if (score >= 80) return 'success';
  if (score >= 60) return 'warning';
  if (score >= 40) return 'secondary';
  return 'destructive';
}

function proficiencyGapBadge(gap: number): { label: string; variant: BadgeVariant } {
  if (gap > 0) return { label: `+${gap}`, variant: 'success' };
  if (gap === 0) return { label: '충족', variant: 'warning' };
  return { label: `${gap}`, variant: 'destructive' };
}

function availabilityBadge(label: string): { label: string; variant: BadgeVariant } {
  if (label === '가능') return { label: '가능', variant: 'success' };
  if (label === '애매') return { label: '애매', variant: 'warning' };
  return { label: '빠듯', variant: 'destructive' };
}

function progressColor(pct: number | null): string {
  if (pct === null) return 'bg-gray-200';
  if (pct >= 90) return 'bg-green-400';
  if (pct >= 50) return 'bg-yellow-400';
  return 'bg-blue-400';
}

function progressLabel(pct: number | null, status: string | null): string {
  if (status === '계획') return '미착수';
  if (pct === null) return '정보없음';
  if (pct >= 90) return '거의 완료';
  if (pct >= 50) return '진행중';
  return '초기';
}

// ============================================
// Tab 1: Candidates
// ============================================

function CandidatesTab({
  projectName,
  categories,
}: {
  projectName: string;
  categories: { name: string; skills: string[] }[];
}) {
  const [skillFilter, setSkillFilter] = useState<string>('');
  const [minProf, setMinProf] = useState<string>('');
  const findCandidates = useFindCandidates();

  const allSkills = categories.flatMap((c) => c.skills).sort();

  const handleSearch = () => {
    findCandidates.mutate({
      project_name: projectName,
      skill_name: skillFilter || undefined,
      min_proficiency: minProf ? parseInt(minProf) : undefined,
    });
  };

  const data: FindCandidatesResponse | undefined = findCandidates.data;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[180px] flex-1">
              <label className="mb-1 block text-sm font-medium">스킬</label>
              <Select
                value={skillFilter}
                onChange={(e) => setSkillFilter(e.target.value)}
              >
                <option value="">전체 스킬</option>
                {allSkills.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </div>
            <div className="w-[140px]">
              <label className="mb-1 block text-sm font-medium">
                최소 숙련도
              </label>
              <Select
                value={minProf}
                onChange={(e) => setMinProf(e.target.value)}
              >
                <option value="">제한 없음</option>
                <option value="1">1 (초급)</option>
                <option value="2">2 (중급)</option>
                <option value="3">3 (고급)</option>
                <option value="4">4 (전문가)</option>
              </Select>
            </div>
            <Button
              onClick={handleSearch}
              disabled={findCandidates.isPending}
            >
              {findCandidates.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Search className="mr-2 h-4 w-4" />
              )}
              탐색
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {findCandidates.isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            {(findCandidates.error as Error)?.message || '후보자 탐색 실패'}
          </CardContent>
        </Card>
      )}

      {data && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              결과: {data.total_skills}개 스킬, {data.total_candidates}명 후보
              {data.project_budget != null && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  예산 {formatKRW(data.project_budget * 1_000_000)}
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {data.skill_candidates.map((sc) => (
                <SkillCandidateCard key={sc.skill_name} sc={sc} />
              ))}
              {data.skill_candidates.length === 0 && (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  REQUIRES 관계가 설정된 스킬이 없습니다
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

const CANDIDATES_INITIAL_SHOW = 5;

function SkillCandidateCard({ sc }: { sc: SkillCandidates }) {
  const badge = importanceBadge(sc.importance);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const toggleRow = (name: string) => {
    setExpandedRow((prev) => (prev === name ? null : name));
  };

  const hasMore = sc.candidates.length > CANDIDATES_INITIAL_SHOW;
  const visibleCandidates = showAll
    ? sc.candidates
    : sc.candidates.slice(0, CANDIDATES_INITIAL_SHOW);
  const hiddenCount = sc.candidates.length - CANDIDATES_INITIAL_SHOW;

  return (
    <div className="rounded-lg border p-3">
      <div className="mb-2 flex items-center gap-2">
        <Badge variant={badge.variant}>{badge.label}</Badge>
        <span className="font-medium">{sc.skill_name}</span>
        {sc.required_proficiency != null && (
          <span className="text-xs text-muted-foreground">
            req&ge;{sc.required_proficiency}
          </span>
        )}
        {sc.required_headcount != null && (
          <span className="text-xs text-muted-foreground">
            hc={sc.required_headcount}
          </span>
        )}
        {sc.max_hourly_rate != null && (
          <span className="text-xs text-muted-foreground">
            max {formatRate(sc.max_hourly_rate)}
          </span>
        )}
        <span className="text-xs text-muted-foreground ml-auto">
          {sc.candidates.length}명
        </span>
      </div>

      {sc.candidates.length > 0 ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[32px]" />
                <TableHead className="w-[80px] text-center">투입</TableHead>
                <TableHead className="w-[100px]">이름</TableHead>
                <TableHead>부서</TableHead>
                <TableHead className="text-center">숙련도</TableHead>
                <TableHead className="text-right">단가/시간</TableHead>
                <TableHead>참여현황</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleCandidates.map((c) => (
                <CandidateRow
                  key={c.employee_name}
                  c={c}
                  isExpanded={expandedRow === c.employee_name}
                  onToggle={() => toggleRow(c.employee_name)}
                />
              ))}
            </TableBody>
          </Table>
          {hasMore && (
            <button
              type="button"
              onClick={() => setShowAll((prev) => !prev)}
              className="mt-2 w-full rounded-md border border-dashed py-1.5 text-xs text-muted-foreground hover:bg-muted/50 transition-colors"
            >
              {showAll ? '접기' : `+${hiddenCount}명 더보기`}
            </button>
          )}
        </>
      ) : (
        <p className="py-2 text-sm text-muted-foreground">후보 없음</p>
      )}
    </div>
  );
}

function CandidateRow({
  c,
  isExpanded,
  onToggle,
}: {
  c: CandidateInfo;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const availBadge = availabilityBadge(c.availability_label ?? '가능');
  const gapBadge = proficiencyGapBadge(c.proficiency_gap);
  const workloadPct = c.max_projects > 0
    ? (c.effective_workload / c.max_projects * 100).toFixed(0)
    : '0';

  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-muted/50"
        onClick={onToggle}
      >
        <TableCell className="w-[32px] px-2">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </TableCell>
        <TableCell className="text-center">
          <Badge variant={availBadge.variant} className="whitespace-nowrap">{availBadge.label}</Badge>
        </TableCell>
        <TableCell className="font-medium">
          {c.employee_name}
        </TableCell>
        <TableCell className="text-muted-foreground">
          {c.department || '-'}
        </TableCell>
        <TableCell className="text-center">
          {proficiencyLabel(c.proficiency)}
          {' '}
          <Badge variant={gapBadge.variant} className="ml-1 px-1 py-0 text-[10px]">
            {gapBadge.label}
          </Badge>
        </TableCell>
        <TableCell className="text-right">
          <span>{formatRate(c.effective_rate)}</span>
          {c.cost_efficiency != null && (
            <span className="ml-1 text-xs text-muted-foreground">
              ({c.cost_efficiency.toFixed(0)}%)
            </span>
          )}
        </TableCell>
        <TableCell className="text-sm text-muted-foreground">
          {c.current_projects}건 (부담 {workloadPct}%)
        </TableCell>
      </TableRow>
      {isExpanded && (
        <TableRow>
          <TableCell colSpan={7} className="bg-muted/30 px-6 py-3">
            <div className="space-y-2">
              {/* 프로젝트 참여 목록 */}
              <div>
                <span className="text-xs font-medium">프로젝트 참여 현황</span>
                {(c.project_participations ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground mt-1">
                    참여 프로젝트 없음 (즉시 투입 가능)
                  </p>
                ) : (
                  <div className="mt-1 space-y-1.5">
                    {c.project_participations.map((p) => (
                      <div key={p.project_name} className="flex items-center gap-2 text-sm">
                        <span className="w-32 truncate font-medium">{p.project_name}</span>
                        <Badge variant="outline" className="text-xs">{p.status || '-'}</Badge>
                        {/* 프로그레스 바 */}
                        <div className="flex-1 h-2 bg-gray-100 rounded-full max-w-[120px]">
                          <div
                            className={`h-full rounded-full ${progressColor(p.progress_pct)}`}
                            style={{ width: `${Math.min(p.progress_pct ?? 0, 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground w-16">
                          {progressLabel(p.progress_pct, p.status)}
                        </span>
                        {p.contribution_pct != null && (
                          <span className="text-xs text-muted-foreground">
                            투입 {p.contribution_pct}%
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              {/* 추천 사유 + 매칭 점수 (부가 정보) */}
              <div className="flex gap-4 text-xs text-muted-foreground mt-2">
                <span>매칭 {c.match_score}점</span>
                {c.match_reasons.map((r, i) => (
                  <span key={i}>&middot; {r}</span>
                ))}
              </div>
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

// ============================================
// Tab 2: Staffing Plan
// ============================================

function StaffingPlanTab({ projectName }: { projectName: string }) {
  const [topN, setTopN] = useState<string>('3');
  const generatePlan = useGenerateStaffingPlan();

  const handleGenerate = () => {
    generatePlan.mutate({
      project_name: projectName,
      top_n_per_skill: parseInt(topN) || 3,
    });
  };

  const data: StaffingPlanResponse | undefined = generatePlan.data;

  return (
    <div className="space-y-4">
      {/* Controls */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-end gap-3">
            <div className="w-[180px]">
              <label className="mb-1 block text-sm font-medium">
                스킬당 추천 인원
              </label>
              <Select
                value={topN}
                onChange={(e) => setTopN(e.target.value)}
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={String(n)}>
                    {n}명
                  </option>
                ))}
              </Select>
            </div>
            <Button
              onClick={handleGenerate}
              disabled={generatePlan.isPending}
            >
              {generatePlan.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ClipboardList className="mr-2 h-4 w-4" />
              )}
              플랜 생성
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {generatePlan.isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            {(generatePlan.error as Error)?.message || '플랜 생성 실패'}
          </CardContent>
        </Card>
      )}

      {/* Summary */}
      {data && (
        <>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">비용 요약</CardTitle>
            </CardHeader>
            <CardContent>
              {data.skill_plans.length > 0 ? (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <p className="text-sm text-muted-foreground">총 예상 인건비</p>
                    <p className="text-2xl font-bold">
                      {formatKRW(data.total_estimated_labor_cost)}
                    </p>
                  </div>
                  {data.project_budget != null && (
                    <div>
                      <p className="text-sm text-muted-foreground">프로젝트 예산</p>
                      <p className="text-2xl font-bold">
                        {formatKRW(data.project_budget * 1_000_000)}
                      </p>
                    </div>
                  )}
                  {data.budget_utilization_percent != null && (
                    <div>
                      <p className="mb-1 text-sm text-muted-foreground">
                        예산 활용률
                      </p>
                      <p className="mb-1 text-2xl font-bold">
                        {data.budget_utilization_percent}%
                      </p>
                      <Progress
                        value={Math.min(data.budget_utilization_percent, 100)}
                      />
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  이 프로젝트에 REQUIRES 스킬이 설정되지 않아 비용을 추정할 수 없습니다.
                  후보자 탐색 탭에서 REQUIRES 관계를 확인하세요.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Skill Plans */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">스킬별 추천</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {data.skill_plans.map((sp) => {
                  const badge = importanceBadge(sp.importance);
                  return (
                    <div
                      key={sp.skill_name}
                      className="rounded-lg border p-3"
                    >
                      <div className="mb-2 flex items-center gap-2">
                        <Badge variant={badge.variant}>{badge.label}</Badge>
                        <span className="font-medium">{sp.skill_name}</span>
                        {sp.required_headcount != null && (
                          <span className="text-xs text-muted-foreground">
                            필요 {sp.required_headcount}명
                          </span>
                        )}
                        <span className="ml-auto text-sm text-muted-foreground">
                          {formatRate(sp.estimated_cost_per_hour)}/h
                        </span>
                      </div>
                      {sp.recommended_candidates.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {sp.recommended_candidates.map((rc) => (
                            <div
                              key={rc.employee_name}
                              className="flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-sm"
                              title={rc.match_reasons.join(' / ')}
                            >
                              <Badge
                                variant={matchScoreBadgeVariant(rc.match_score)}
                                className="px-1.5 py-0 text-[10px]"
                              >
                                {rc.match_score}
                              </Badge>
                              <span className="font-medium">
                                {rc.employee_name}
                              </span>
                              <span className="text-muted-foreground">
                                ({proficiencyLabel(rc.proficiency)})
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {formatRate(rc.effective_rate)}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          추천 후보 없음
                        </p>
                      )}
                    </div>
                  );
                })}
                {data.skill_plans.length === 0 && (
                  <p className="py-4 text-center text-sm text-muted-foreground">
                    스킬 플랜이 없습니다
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

// ============================================
// Tab 3: Budget Analysis
// ============================================

function BudgetAnalysisTab({ projectName }: { projectName: string }) {
  const analyzeBudget = useAnalyzeBudget();

  const handleAnalyze = () => {
    analyzeBudget.mutate({ project_name: projectName });
  };

  const data: BudgetAnalysisResponse | undefined = analyzeBudget.data;

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-4">
          <Button
            onClick={handleAnalyze}
            disabled={analyzeBudget.isPending}
          >
            {analyzeBudget.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <TrendingDown className="mr-2 h-4 w-4" />
            )}
            예산 분석
          </Button>
        </CardContent>
      </Card>

      {/* Error */}
      {analyzeBudget.isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            {(analyzeBudget.error as Error)?.message || '예산 분석 실패'}
          </CardContent>
        </Card>
      )}

      {data && (
        <>
          {/* Summary Cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">계획 인건비</p>
                <p className="text-2xl font-bold">
                  {formatKRW(data.total_planned_cost)}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">실제 인건비</p>
                <p className="text-2xl font-bold">
                  {formatKRW(data.total_actual_cost)}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">차이</p>
                <p
                  className={`text-2xl font-bold ${
                    data.variance > 0
                      ? 'text-destructive'
                      : data.variance < 0
                        ? 'text-green-600'
                        : ''
                  }`}
                >
                  {formatKRW(data.variance)}
                  {data.variance_percent != null && (
                    <span className="ml-1 text-base">
                      ({data.variance_percent > 0 ? '+' : ''}
                      {data.variance_percent}%)
                    </span>
                  )}
                </p>
              </CardContent>
            </Card>
            {data.project_budget != null && data.project_budget > 0 && (() => {
              const burnRate = (data.total_actual_cost / (data.project_budget * 1_000_000)) * 100;
              return (
                <Card>
                  <CardContent className="pt-4">
                    <p className="mb-1 text-sm text-muted-foreground">예산 소진율</p>
                    <p className="mb-1 text-2xl font-bold">
                      {burnRate.toFixed(1)}%
                    </p>
                    <Progress value={Math.min(burnRate, 100)} />
                  </CardContent>
                </Card>
              );
            })()}
          </div>

          {/* Budget info */}
          {(data.project_budget != null || data.budget_allocated != null || data.budget_spent != null) && (
            <Card>
              <CardContent className="pt-4">
                <div className="flex flex-wrap gap-6 text-sm">
                  {data.project_budget != null && (
                    <div>
                      <span className="text-muted-foreground">프로젝트 예산: </span>
                      <span className="font-medium">{formatKRW(data.project_budget * 1_000_000)}</span>
                    </div>
                  )}
                  {data.budget_allocated != null && (
                    <div>
                      <span className="text-muted-foreground">배정 예산: </span>
                      <span className="font-medium">{formatKRW(data.budget_allocated)}</span>
                    </div>
                  )}
                  {data.budget_spent != null && (
                    <div>
                      <span className="text-muted-foreground">집행 예산: </span>
                      <span className="font-medium">{formatKRW(data.budget_spent)}</span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Team Breakdown Table */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                팀원별 비용 내역 ({data.team_breakdown.length}명)
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.team_breakdown.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>이름</TableHead>
                      <TableHead>역할</TableHead>
                      <TableHead className="text-right">단가/h</TableHead>
                      <TableHead className="text-right">배정 시간</TableHead>
                      <TableHead className="text-right">실제 시간</TableHead>
                      <TableHead className="text-right">계획 비용</TableHead>
                      <TableHead className="text-right">실제 비용</TableHead>
                      <TableHead className="text-right">차이</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.team_breakdown.map((tm) => {
                      const diff = tm.actual_cost - tm.planned_cost;
                      const diffPct =
                        tm.planned_cost > 0
                          ? ((diff / tm.planned_cost) * 100).toFixed(0)
                          : '-';
                      return (
                        <TableRow key={tm.employee_name}>
                          <TableCell className="font-medium">
                            {tm.employee_name}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {tm.role || '-'}
                          </TableCell>
                          <TableCell className="text-right">
                            {formatRate(tm.agreed_rate)}
                          </TableCell>
                          <TableCell className="text-right">
                            {tm.allocated_hours.toLocaleString('ko-KR')}h
                          </TableCell>
                          <TableCell className="text-right">
                            {tm.actual_hours.toLocaleString('ko-KR')}h
                          </TableCell>
                          <TableCell className="text-right">
                            {formatKRW(tm.planned_cost)}
                          </TableCell>
                          <TableCell className="text-right">
                            {formatKRW(tm.actual_cost)}
                          </TableCell>
                          <TableCell
                            className={`text-right ${
                              diff > 0
                                ? 'text-destructive'
                                : diff < 0
                                  ? 'text-green-600'
                                  : ''
                            }`}
                          >
                            {diffPct !== '-' ? `${Number(diffPct) > 0 ? '+' : ''}${diffPct}%` : '-'}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              ) : (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  배치된 팀원이 없습니다
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

// ============================================
// Main Component
// ============================================

export function ProjectStaffing() {
  const [selectedProject, setSelectedProject] = useState<string>('');
  const { data: projectsData, isLoading: projectsLoading } =
    useStaffingProjects();
  const { data: categoriesData } = useStaffingCategories();

  const projects = projectsData?.projects ?? [];
  const categories = categoriesData?.categories ?? [];

  return (
    <div className="space-y-4">
      {/* Project Selector */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-3">
            <label htmlFor="project-select" className="text-sm font-medium whitespace-nowrap">
              프로젝트 선택
            </label>
            <Select
              id="project-select"
              value={selectedProject}
              onChange={(e) => setSelectedProject(e.target.value)}
              className="max-w-md"
            >
              <option value="">
                {projectsLoading ? '로딩 중...' : '프로젝트를 선택하세요'}
              </option>
              {projects.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name}
                  {p.status ? ` [${p.status}]` : ''}
                </option>
              ))}
            </Select>
            {(() => {
              const selected = projects.find((p) => p.name === selectedProject);
              return selected?.budget_million != null ? (
                <span className="text-sm text-muted-foreground">
                  예산: {formatKRW(selected.budget_million * 1_000_000)}
                </span>
              ) : null;
            })()}
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      {selectedProject ? (
        <Tabs defaultValue="candidates" className="w-full" key={selectedProject}>
          <TabsList>
            <TabsTrigger value="candidates">후보자 탐색</TabsTrigger>
            <TabsTrigger value="plan">스태핑 플랜</TabsTrigger>
            <TabsTrigger value="budget">예산 분석</TabsTrigger>
          </TabsList>
          <div className="mt-4">
            <TabsContent value="candidates" className="m-0">
              <CandidatesTab
                projectName={selectedProject}
                categories={categories}
              />
            </TabsContent>
            <TabsContent value="plan" className="m-0">
              <StaffingPlanTab projectName={selectedProject} />
            </TabsContent>
            <TabsContent value="budget" className="m-0">
              <BudgetAnalysisTab projectName={selectedProject} />
            </TabsContent>
          </div>
        </Tabs>
      ) : (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            프로젝트를 선택하면 스태핑 분석을 시작할 수 있습니다
          </CardContent>
        </Card>
      )}
    </div>
  );
}
