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
import { Loader2, Search, ClipboardList, TrendingDown } from 'lucide-react';
import type {
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

function SkillCandidateCard({ sc }: { sc: SkillCandidates }) {
  const badge = importanceBadge(sc.importance);

  return (
    <div className="rounded-lg border p-3">
      <div className="mb-2 flex items-center gap-2">
        <Badge variant={badge.variant}>{badge.label}</Badge>
        <span className="font-medium">{sc.skill_name}</span>
        {sc.required_proficiency != null && (
          <span className="text-xs text-muted-foreground">
            req≥{sc.required_proficiency}
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
      </div>

      {sc.candidates.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[100px]">이름</TableHead>
              <TableHead>부서</TableHead>
              <TableHead className="text-center">숙련도</TableHead>
              <TableHead className="text-right">단가/시간</TableHead>
              <TableHead className="text-center">상태</TableHead>
              <TableHead className="text-center">프로젝트</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sc.candidates.map((c) => (
              <TableRow key={c.employee_name}>
                <TableCell className="font-medium">
                  {c.employee_name}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {c.department || '-'}
                </TableCell>
                <TableCell className="text-center">
                  {proficiencyLabel(c.proficiency)}
                </TableCell>
                <TableCell className="text-right">
                  {formatRate(c.effective_rate)}
                </TableCell>
                <TableCell className="text-center">
                  {c.availability || '-'}
                </TableCell>
                <TableCell className="text-center">
                  {c.current_projects}/{c.max_projects}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <p className="py-2 text-sm text-muted-foreground">후보 없음</p>
      )}
    </div>
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
                              className="flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-sm"
                            >
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
