import React from 'react';
import { Brain, Clock, Route } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { StepItem } from './StepItem';
import { ExpansionTree } from './ExpansionTree';
import { cn } from '@/lib/utils';
import type { ThoughtProcessVisualization } from '@/types/api';

interface ThinkingPanelProps {
  thoughtProcess: ThoughtProcessVisualization | null;
  className?: string;
}

export function ThinkingPanel({ thoughtProcess, className }: ThinkingPanelProps) {
  if (!thoughtProcess) {
    return (
      <div className={cn('flex h-full items-center justify-center p-8', className)}>
        <div className="text-center text-muted-foreground">
          <Brain className="mx-auto h-12 w-12 opacity-50" />
          <p className="mt-4 text-lg font-medium">No Thinking Process</p>
          <p className="text-sm mt-2">질문을 입력하면 추론 과정이 표시됩니다.</p>
        </div>
      </div>
    );
  }

  const { steps, concept_expansions, total_duration_ms, execution_path } = thoughtProcess;

  return (
    <div className={cn('flex h-full flex-col', className)}>
      {/* Header */}
      <div className="border-b border-border px-4 py-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Brain className="h-5 w-5" />
          Thinking Process
        </h2>
        {total_duration_ms !== undefined && (
          <div className="mt-1 flex items-center gap-1 text-sm text-muted-foreground">
            <Clock className="h-4 w-4" />
            <span>Total: {total_duration_ms}ms</span>
          </div>
        )}
      </div>

      <ScrollArea className="flex-1 h-0 min-h-0">
        <div className="p-4 space-y-6">
          {/* Execution Path */}
          {execution_path.length > 0 && (
            <div>
              <h3 className="flex items-center gap-2 text-sm font-medium mb-2">
                <Route className="h-4 w-4" />
                Execution Path
              </h3>
              <div className="flex flex-wrap items-center gap-1">
                {execution_path.map((node, idx) => (
                  <React.Fragment key={idx}>
                    <span className="rounded bg-secondary px-2 py-1 text-xs">
                      {node}
                    </span>
                    {idx < execution_path.length - 1 && (
                      <span className="text-muted-foreground">→</span>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}

          {/* Steps */}
          {steps.length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-3">Steps</h3>
              <div>
                {steps.map((step, idx) => (
                  <StepItem
                    key={step.step_number}
                    step={step}
                    isLast={idx === steps.length - 1}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Concept Expansions */}
          {concept_expansions.length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-3">Concept Expansions</h3>
              <div className="space-y-3">
                {concept_expansions.map((tree, idx) => (
                  <ExpansionTree key={idx} tree={tree} />
                ))}
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

export default ThinkingPanel;
