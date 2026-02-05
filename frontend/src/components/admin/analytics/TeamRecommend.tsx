import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useRecommendTeam } from '@/api/hooks/admin/useAnalytics';
import { Users, Loader2, Sparkles, X } from 'lucide-react';
import type { TeamRecommendResponse } from '@/types/admin';

export function TeamRecommend() {
  const [skillInput, setSkillInput] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [teamSize, setTeamSize] = useState(5);
  const [result, setResult] = useState<TeamRecommendResponse | null>(null);

  const recommendTeam = useRecommendTeam();

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

  const handleRecommend = () => {
    if (skills.length === 0) return;

    recommendTeam.mutate(
      { required_skills: skills, team_size: teamSize },
      {
        onSuccess: (data) => setResult(data),
      }
    );
  };

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-lg">Team Recommendation</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Skills Input */}
        <div className="space-y-2">
          <label htmlFor="skills" className="text-sm font-medium">
            Required Skills
          </label>
          <Input
            id="skills"
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

        {/* Team Size */}
        <div className="flex items-end gap-4">
          <div className="space-y-2">
            <label htmlFor="teamSize" className="text-sm font-medium">
              Team Size
            </label>
            <Input
              id="teamSize"
              type="number"
              min={2}
              max={20}
              value={teamSize}
              onChange={(e) => {
                const value = parseInt(e.target.value, 10);
                setTeamSize(Number.isNaN(value) ? 5 : Math.min(Math.max(value, 2), 20));
              }}
              className="w-24"
            />
          </div>
          <Button onClick={handleRecommend} disabled={recommendTeam.isPending || skills.length === 0}>
            {recommendTeam.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 h-4 w-4" />
            )}
            Recommend
          </Button>
        </div>

        {/* Error */}
        {recommendTeam.error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700" role="alert">
            {recommendTeam.error instanceof Error
              ? recommendTeam.error.message
              : 'An error occurred'}
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="space-y-4 pt-4 border-t">
            {/* Coverage */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Skill Coverage</span>
                <span className="font-medium">{(result.skill_coverage * 100).toFixed(0)}%</span>
              </div>
              <Progress value={result.skill_coverage * 100} />
            </div>

            {/* Skills Status */}
            <div className="flex flex-wrap gap-2">
              {result.covered_skills.map((skill) => (
                <Badge key={skill} variant="success">
                  {skill}
                </Badge>
              ))}
              {result.missing_skills.map((skill) => (
                <Badge key={skill} variant="destructive">
                  {skill}
                </Badge>
              ))}
            </div>

            {/* Team Members */}
            <div className="space-y-2">
              <p className="text-sm font-medium">
                Recommended Team ({result.members.length} members, {result.community_diversity} communities)
              </p>
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {result.members.map((member) => (
                  <div key={member.name} className="flex items-center gap-3 rounded-lg border p-3">
                    <Users className="h-4 w-4 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium">{member.name}</p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {member.matched_skills.map((skill) => (
                          <Badge key={skill} variant="outline" className="text-xs">
                            {skill}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    {member.community_id !== null && (
                      <Badge variant="secondary">C{member.community_id}</Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
