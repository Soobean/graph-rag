import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Send, Loader2, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useStreamingQuery } from '@/api/hooks';
import type { StreamingMetadata } from '@/types/api';
import type { DemoRole } from '@/stores/uiStore';
import { cn } from '@/lib/utils';

const ROLES: { role: DemoRole; label: string; emoji: string; color: string; subtitle: string }[] = [
  { role: 'admin', label: 'admin', emoji: '\uD83D\uDC51', color: 'border-red-300 bg-red-50', subtitle: '\uBAA8\uB4E0 \uAD8C\uD55C' },
  { role: 'manager', label: 'manager', emoji: '\uD83D\uDCCA', color: 'border-blue-300 bg-blue-50', subtitle: '\uBC31\uC5D4\uB4DC\uAC1C\uBC1C\uD300' },
  { role: 'editor', label: 'editor', emoji: '\u270F\uFE0F', color: 'border-green-300 bg-green-50', subtitle: '\uC77D\uAE30/\uC4F0\uAE30' },
  { role: 'viewer', label: 'viewer', emoji: '\uD83D\uDC41', color: 'border-gray-300 bg-gray-50', subtitle: '\uC77D\uAE30 \uC804\uC6A9' },
];

interface FilterAnalysis {
  resultCount: number;
  hasSalary: boolean;
  hasCompany: boolean;
  hasMentors: boolean;
}

function analyzeFiltering(metadata: StreamingMetadata | null): FilterAnalysis | null {
  if (!metadata) return null;

  const graphData = metadata.graph_data;
  let hasSalary = false;
  let hasCompany = false;
  let hasMentors = false;

  if (graphData) {
    hasCompany = graphData.nodes.some((n) => n.label === 'Company');
    hasSalary = graphData.nodes.some(
      (n) => n.label === 'Employee' && 'salary' in n.properties
    );
    hasMentors = graphData.edges.some((e) => e.label === 'MENTORS');
  }

  return {
    resultCount: metadata.result_count,
    hasSalary,
    hasCompany,
    hasMentors,
  };
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
}

function RoleColumn({ role, content, metadata, isStreaming, error }: RoleColumnProps) {
  const analysis = useMemo(() => analyzeFiltering(metadata), [metadata]);

  return (
    <div className={cn('flex flex-col rounded-lg border-2 overflow-hidden', role.color)}>
      {/* Role Header */}
      <div className="border-b px-3 py-2">
        <div className="flex items-center gap-1.5">
          <span className="text-base">{role.emoji}</span>
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
          <FilterBadge label="salary" value={analysis.hasSalary} />
          <FilterBadge label="Company" value={analysis.hasCompany} />
          <FilterBadge label="MENTORS" value={analysis.hasMentors} />
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

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = input.trim();
      if (!trimmed || isAnyStreaming) return;

      setSubmitted(true);

      ROLES.forEach((roleConfig, idx) => {
        queriesRef.current[idx].startStreaming(
          { question: trimmed },
          { demoRole: roleConfig.role }
        );
      });
    },
    [input, isAnyStreaming]
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
            placeholder="Compare query across roles (e.g. Python \uAC1C\uBC1C\uC790 \uCC3E\uC544\uC918)"
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

      {/* Compare Grid */}
      <main className="relative flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 min-h-[500px]">
          {ROLES.map((roleConfig, idx) => (
            <RoleColumn
              key={roleConfig.role}
              role={roleConfig}
              content={queries[idx].state.content}
              metadata={queries[idx].state.metadata}
              isStreaming={queries[idx].state.isStreaming}
              error={queries[idx].state.error}
            />
          ))}
        </div>
        {!submitted && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <p className="text-muted-foreground text-sm">
              Enter a question above to compare results across all 4 roles
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
