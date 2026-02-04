import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useAnalyzeSkillGap, useRecommendGapSolution } from '@/api/hooks/admin';
import { Users, Loader2, Search, X, ChevronDown, ChevronRight, UserPlus } from 'lucide-react';
import type {
  SkillGapAnalyzeResponse,
  SkillRecommendResponse,
  SkillCoverage,
  CoverageStatus,
  RecommendedEmployee,
} from '@/types/admin';

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
      {/* Available Candidates */}
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

      {/* Busy Candidates - Alternative */}
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

  const getCategoryColor = (color: string) => {
    const colorMap: Record<string, string> = {
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
    return colorMap[color] || 'bg-gray-500';
  };

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-lg">Skill Gap Analysis</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Required Skills Input */}
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
            <div className="flex flex-wrap gap-2">
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

        {/* Team Source Toggle */}
        <div className="space-y-2">
          <label className="text-sm font-medium">Team Source</label>
          <div className="flex gap-2">
            <Button
              variant={teamMode === 'members' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setTeamMode('members')}
            >
              <Users className="mr-2 h-4 w-4" />
              Members
            </Button>
            <Button
              variant={teamMode === 'project' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setTeamMode('project')}
            >
              <Search className="mr-2 h-4 w-4" />
              Project
            </Button>
          </div>
        </div>

        {/* Team Members Input */}
        {teamMode === 'members' && (
          <div className="space-y-2">
            <label htmlFor="team-members" className="text-sm font-medium">
              Team Members
            </label>
            <Input
              id="team-members"
              value={memberInput}
              onChange={(e) => setMemberInput(e.target.value)}
              onKeyDown={handleAddMember}
              placeholder="Type a member name and press Enter..."
            />
            {members.length > 0 && (
              <div className="flex flex-wrap gap-2">
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
          </div>
        )}

        {/* Project ID Input */}
        {teamMode === 'project' && (
          <div className="space-y-2">
            <label htmlFor="project-id" className="text-sm font-medium">
              Project ID
            </label>
            <Input
              id="project-id"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              placeholder="Enter project ID..."
            />
          </div>
        )}

        {/* Analyze Button */}
        <Button onClick={handleAnalyze} disabled={analyzeGap.isPending || !canAnalyze}>
          {analyzeGap.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Search className="mr-2 h-4 w-4" />
          )}
          Analyze
        </Button>

        {/* Error */}
        {analyzeGap.error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700" role="alert">
            {analyzeGap.error instanceof Error ? analyzeGap.error.message : 'An error occurred'}
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="space-y-4 border-t pt-4">
            {/* Summary */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">
                  {result.team_members.length} team members
                </span>
              </div>
              <Badge variant={STATUS_BADGE_VARIANT[result.overall_status]}>
                {STATUS_LABEL[result.overall_status]}
              </Badge>
            </div>

            {/* Category Summary */}
            <div className="space-y-3">
              <p className="text-sm font-medium">Category Coverage</p>
              {result.category_summary.map((cat) => (
                <div key={cat.category} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-2 w-2 rounded-full ${getCategoryColor(cat.color)}`}
                      />
                      <span>{cat.category}</span>
                    </div>
                    <span className="text-muted-foreground">
                      {cat.covered_count}/{cat.total_skills} ({(cat.coverage_ratio * 100).toFixed(0)}%)
                    </span>
                  </div>
                  <Progress value={cat.coverage_ratio * 100} className="h-2" />
                </div>
              ))}
            </div>

            {/* Skill Details */}
            <div className="space-y-2">
              <p className="text-sm font-medium">Skill Details</p>
              <div className="max-h-[400px] space-y-2 overflow-y-auto">
                {result.skill_details.map((detail) => (
                  <div key={detail.skill} className="rounded-lg border">
                    <button
                      type="button"
                      className="flex w-full items-center justify-between p-3 text-left hover:bg-muted/50"
                      onClick={() => handleSkillClick(detail)}
                      disabled={detail.status === 'covered'}
                    >
                      <div className="flex items-center gap-2">
                        {detail.status !== 'covered' ? (
                          expandedSkill === detail.skill ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )
                        ) : (
                          <span className="w-4" />
                        )}
                        <span className="font-medium">{detail.skill}</span>
                        <span className="text-xs text-muted-foreground">({detail.category})</span>
                      </div>
                      <Badge variant={STATUS_BADGE_VARIANT[detail.status]}>
                        {STATUS_LABEL[detail.status]}
                      </Badge>
                    </button>

                    {/* Skill Detail Expanded */}
                    {expandedSkill === detail.skill && (
                      <div className="border-t bg-muted/30 p-3 space-y-3">
                        <p className="text-sm text-muted-foreground">{detail.explanation}</p>

                        {/* Existing Matches */}
                        {(detail.exact_matches.length > 0 || detail.similar_matches.length > 0) && (
                          <div className="space-y-2">
                            <p className="text-xs font-medium text-muted-foreground">
                              Current Team Coverage
                            </p>
                            {detail.exact_matches.map((match, idx) => (
                              <div
                                key={`exact-${idx}`}
                                className="flex items-center gap-2 text-sm"
                              >
                                <Badge variant="success" className="text-xs">
                                  Exact
                                </Badge>
                                <span>{match.employee_name}</span>
                                <span className="text-muted-foreground">({match.possessed_skill})</span>
                              </div>
                            ))}
                            {detail.similar_matches.map((match, idx) => (
                              <div
                                key={`similar-${idx}`}
                                className="flex items-center gap-2 text-sm"
                              >
                                <Badge variant="outline" className="text-xs">
                                  Similar
                                </Badge>
                                <span>{match.employee_name}</span>
                                <span className="text-muted-foreground">({match.possessed_skill})</span>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Recommendations */}
                        {recommendations[detail.skill] ? (
                          <CandidateRecommendations
                            candidates={recommendations[detail.skill].internal_candidates}
                            externalSearchQuery={recommendations[detail.skill].external_search_query}
                          />
                        ) : recommendSolution.isPending && expandedSkill === detail.skill ? (
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Loading recommendations...
                          </div>
                        ) : recommendSolution.error && expandedSkill === detail.skill ? (
                          <p className="text-sm text-red-600">
                            Failed to load recommendations
                          </p>
                        ) : null}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Gaps Summary */}
            {result.gaps.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">Gap Skills ({result.gaps.length})</p>
                <div className="flex flex-wrap gap-2">
                  {result.gaps.map((gap) => (
                    <Badge key={gap} variant="destructive">
                      {gap}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Recommendations Summary */}
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
          </div>
        )}
      </CardContent>
    </Card>
  );
}
