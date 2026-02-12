import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Send, Loader2, Check, X, ShieldCheck, Users, PenLine, Eye, ChevronDown, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useStreamingQuery } from '@/api/hooks';
import { CompareDataTable } from '@/components/compare/CompareDataTable';
import type { StreamingMetadata } from '@/types/api';
import type { DemoRole } from '@/stores/uiStore';
import { cn } from '@/lib/utils';

const ROLES: { role: DemoRole; label: string; icon: LucideIcon; color: string; iconColor: string; subtitle: string }[] = [
  { role: 'admin', label: 'admin', icon: ShieldCheck, color: 'border-red-300 bg-red-50', iconColor: 'text-red-600', subtitle: '모든 권한' },
  { role: 'manager', label: 'manager', icon: Users, color: 'border-blue-300 bg-blue-50', iconColor: 'text-blue-600', subtitle: '백엔드개발팀' },
  { role: 'editor', label: 'editor', icon: PenLine, color: 'border-green-300 bg-green-50', iconColor: 'text-green-600', subtitle: '읽기/쓰기' },
  { role: 'viewer', label: 'viewer', icon: Eye, color: 'border-gray-300 bg-gray-50', iconColor: 'text-gray-500', subtitle: '읽기 전용' },
];

const EXAMPLE_QUERIES = [
  { label: '개발자 단가 비교', query: 'Python 고급 이상 개발자의 단가와 가용 상태를 알려줘' },
  { label: '프로젝트 예산', query: '챗봇 리뉴얼 프로젝트의 예산과 참여 인력의 단가를 알려줘' },
  { label: '멘토링 + 부서', query: '백엔드개발팀 멘토링 관계와 멘토의 프로젝트를 알려줘' },
];

interface FilterAnalysis {
  resultCount: number;
  hasMentors: boolean;
  hasRate: boolean;
  hasBudget: boolean;
  hasEffectiveRate: boolean;
}

/** 배지 정의: label + 분석 결과에서 값 추출하는 키 */
const BADGE_KEYS: { label: string; key: keyof Omit<FilterAnalysis, 'resultCount'> }[] = [
  { label: 'hourly_rate', key: 'hasRate' },
  { label: 'effective_rate', key: 'hasEffectiveRate' },
  { label: 'budget_allocated', key: 'hasBudget' },
  { label: 'MENTORS', key: 'hasMentors' },
];

function analyzeFiltering(metadata: StreamingMetadata | null): FilterAnalysis | null {
  if (!metadata) return null;

  const graphData = metadata.graph_data;
  let hasMentors = false;
  let hasRate = false;
  let hasBudget = false;
  let hasEffectiveRate = false;

  if (graphData) {
    hasRate = graphData.nodes.some(
      (n) => n.label === 'Employee' && 'hourly_rate' in n.properties
    );
    hasBudget = graphData.nodes.some(
      (n) => n.label === 'Project' && 'budget_allocated' in n.properties
    );
    hasMentors = graphData.edges.some((e) => e.label === 'MENTORS');
    hasEffectiveRate = graphData.edges.some(
      (e) => e.label === 'HAS_SKILL' && 'effective_rate' in (e.properties ?? {})
    );
  }

  return {
    resultCount: metadata.result_count,
    hasMentors,
    hasRate,
    hasBudget,
    hasEffectiveRate,
  };
}

/** 4개 역할 분석 결과를 비교해서 '역할 간 차이가 있는' 배지 키만 반환 */
function getVisibleBadges(analyses: (FilterAnalysis | null)[]): (typeof BADGE_KEYS)[number][] {
  return BADGE_KEYS.filter(({ key }) =>
    analyses.some((a) => a?.[key] === true)
  );
}

function FilterBadge({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      {value ? (
        <Check className="h-3.5 w-3.5 text-green-600" />
      ) : (
        <X className="h-3.5 w-3.5 text-red-400" />
      )}
    </div>
  );
}

interface RoleColumnProps {
  role: typeof ROLES[number];
  content: string;
  metadata: StreamingMetadata | null;
  isStreaming: boolean;
  error: string | null;
  visibleBadges: (typeof BADGE_KEYS)[number][];
}

function RoleColumn({ role, content, metadata, isStreaming, error, visibleBadges }: RoleColumnProps) {
  const analysis = useMemo(() => analyzeFiltering(metadata), [metadata]);

  return (
    <div className={cn('flex flex-col rounded-lg border-2 overflow-hidden', role.color)}>
      {/* Role Header */}
      <div className="border-b px-3 py-2">
        <div className="flex items-center gap-1.5">
          <role.icon className={cn('h-4 w-4', role.iconColor)} />
          <span className="font-semibold text-sm">{role.label}</span>
          {isStreaming && <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">{role.subtitle}</p>
      </div>

      {/* Filter Analysis */}
      {analysis && (
        <div className="border-b px-3 py-2 space-y-1 bg-white/50">
          <div className="flex items-center justify-between text-xs font-medium">
            <span>Results</span>
            <span className={cn(
              'font-bold',
              analysis.resultCount === 0 && 'text-red-600',
              analysis.resultCount > 0 && analysis.resultCount < 5 && 'text-amber-600',
            )}>
              {analysis.resultCount}
            </span>
          </div>
          {visibleBadges.map(({ label, key }) => (
            <FilterBadge key={key} label={label} value={analysis[key]} />
          ))}
        </div>
      )}

      {/* Response Content */}
      <div className="flex-1 overflow-y-auto p-3 bg-white/30">
        {error ? (
          <p className="text-xs text-destructive">{error}</p>
        ) : content ? (
          <p className="text-xs leading-relaxed whitespace-pre-wrap">{content}</p>
        ) : isStreaming ? (
          <p className="text-xs text-muted-foreground animate-pulse">Waiting...</p>
        ) : (
          <p className="text-xs text-muted-foreground">Submit a question to compare</p>
        )}
      </div>
    </div>
  );
}

export function ComparePage() {
  const [input, setInput] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [showTextGrid, setShowTextGrid] = useState(false);

  const adminQuery = useStreamingQuery();
  const managerQuery = useStreamingQuery();
  const editorQuery = useStreamingQuery();
  const viewerQuery = useStreamingQuery();

  const queriesRef = useRef([adminQuery, managerQuery, editorQuery, viewerQuery]);
  useEffect(() => {
    queriesRef.current = [adminQuery, managerQuery, editorQuery, viewerQuery];
  });

  const isAnyStreaming =
    adminQuery.state.isStreaming ||
    managerQuery.state.isStreaming ||
    editorQuery.state.isStreaming ||
    viewerQuery.state.isStreaming;

  const submitQuery = useCallback(
    (query: string) => {
      const trimmed = query.trim();
      if (!trimmed || isAnyStreaming) return;

      setInput(trimmed);
      setSubmitted(true);

      ROLES.forEach((roleConfig, idx) => {
        queriesRef.current[idx].startStreaming(
          { question: trimmed },
          { demoRole: roleConfig.role }
        );
      });
    },
    [isAnyStreaming]
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      submitQuery(input);
    },
    [input, submitQuery]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.nativeEvent.isComposing) return;
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit(e);
      }
    },
    [handleSubmit]
  );

  const queries = [adminQuery, managerQuery, editorQuery, viewerQuery];

  // 4역할의 분석 결과를 비교 → 최소 1개 역할에서 ✓인 배지만 표시
  const adminMeta = adminQuery.state.metadata;
  const managerMeta = managerQuery.state.metadata;
  const editorMeta = editorQuery.state.metadata;
  const viewerMeta = viewerQuery.state.metadata;
  const visibleBadges = useMemo(() => {
    const analyses = [adminMeta, managerMeta, editorMeta, viewerMeta].map(analyzeFiltering);
    return getVisibleBadges(analyses);
  }, [adminMeta, managerMeta, editorMeta, viewerMeta]);

  const isAllComplete = queries.every(
    (q) => q.state.isComplete || q.state.error != null
  );

  const metadataByRole = useMemo(
    () => [adminMeta, managerMeta, editorMeta, viewerMeta],
    [adminMeta, managerMeta, editorMeta, viewerMeta]
  );

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
          <h1 className="text-xl font-bold">Access Control Compare</h1>
        </div>
      </header>

      {/* Query Input */}
      <div className="border-b border-border px-4 py-3">
        <form onSubmit={handleSubmit} className="flex items-center gap-2 max-w-3xl mx-auto">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Compare query across roles (e.g. Python 개발자 찾아줘)"
            disabled={isAnyStreaming}
            className="flex-1"
          />
          <Button type="submit" size="icon" disabled={!input.trim() || isAnyStreaming}>
            {isAnyStreaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </form>
      </div>

      {/* Compare Grid / Empty State */}
      <main className="flex-1 overflow-y-auto p-4">
        {submitted ? (
          <div className="space-y-4">
            {/* Data Comparison Table — appears after all streams complete */}
            {(isAllComplete || isAnyStreaming) && (
              <CompareDataTable
                metadataByRole={metadataByRole}
                isComplete={isAllComplete}
              />
            )}

            {/* Text Grid — collapsible after data table appears */}
            {isAllComplete ? (
              <div>
                <button
                  onClick={() => setShowTextGrid((v) => !v)}
                  className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-3"
                >
                  <ChevronDown className={cn('h-4 w-4 transition-transform', showTextGrid && 'rotate-180')} />
                  텍스트 응답 {showTextGrid ? '접기' : '보기'}
                </button>
                {showTextGrid && (
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 min-h-[400px]">
                    {ROLES.map((roleConfig, idx) => (
                      <RoleColumn
                        key={roleConfig.role}
                        role={roleConfig}
                        content={queries[idx].state.content}
                        metadata={queries[idx].state.metadata}
                        isStreaming={queries[idx].state.isStreaming}
                        error={queries[idx].state.error}
                        visibleBadges={visibleBadges}
                      />
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 min-h-[500px]">
                {ROLES.map((roleConfig, idx) => (
                  <RoleColumn
                    key={roleConfig.role}
                    role={roleConfig}
                    content={queries[idx].state.content}
                    metadata={queries[idx].state.metadata}
                    isStreaming={queries[idx].state.isStreaming}
                    error={queries[idx].state.error}
                    visibleBadges={visibleBadges}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
            <div className="flex gap-3">
              {ROLES.map((r) => (
                <div key={r.role} className={cn('rounded-lg border-2 px-3 py-2 flex items-center gap-1.5', r.color)}>
                  <r.icon className={cn('h-4 w-4', r.iconColor)} />
                  <span className="text-xs font-medium">{r.label}</span>
                </div>
              ))}
            </div>
            <p className="text-sm">질문을 입력하면 4개 역할의 결과를 비교합니다</p>
            <div className="flex flex-wrap justify-center gap-2 mt-2">
              {EXAMPLE_QUERIES.map((eq) => (
                <button
                  key={eq.label}
                  onClick={() => submitQuery(eq.query)}
                  className="rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
                >
                  {eq.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
