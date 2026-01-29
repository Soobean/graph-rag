import React from 'react';
import {
  Search,
  Layers,
  Zap,
  Target,
  MessageSquare,
  Database,
  Clock,
  CheckCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ThoughtStep, StepType } from '@/types/api';

interface StepItemProps {
  step: ThoughtStep;
  isLast?: boolean;
}

const stepTypeConfig: Record<StepType, { icon: React.ElementType; color: string }> = {
  classification: { icon: Search, color: 'text-blue-500' },
  decomposition: { icon: Layers, color: 'text-purple-500' },
  extraction: { icon: Target, color: 'text-orange-500' },
  expansion: { icon: Zap, color: 'text-amber-500' },
  resolution: { icon: CheckCircle, color: 'text-green-500' },
  generation: { icon: MessageSquare, color: 'text-pink-500' },
  execution: { icon: Database, color: 'text-cyan-500' },
  response: { icon: MessageSquare, color: 'text-indigo-500' },
  cache: { icon: Clock, color: 'text-gray-500' },
};

export function StepItem({ step, isLast = false }: StepItemProps) {
  const config = stepTypeConfig[step.step_type] || { icon: CheckCircle, color: 'text-gray-500' };
  const Icon = config.icon;

  // Type-safe summaries
  const inputSummary = typeof step.input_summary === 'string' ? step.input_summary : null;
  const outputSummary = typeof step.output_summary === 'string' ? step.output_summary : null;
  const hasSummary = inputSummary !== null || outputSummary !== null;

  return (
    <div className="relative flex gap-3">
      {/* Timeline connector */}
      {!isLast && (
        <div className="absolute left-4 top-10 h-full w-0.5 bg-border" />
      )}

      {/* Step icon */}
      <div
        className={cn(
          'relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-background border-2',
          config.color
        )}
        style={{ borderColor: 'currentColor' }}
      >
        <Icon className="h-4 w-4" />
      </div>

      {/* Step content */}
      <div className="flex-1 pb-6">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">
            Step {step.step_number}
          </span>
          <span className="rounded bg-secondary px-1.5 py-0.5 text-xs capitalize">
            {step.step_type}
          </span>
          {step.duration_ms !== undefined && (
            <span className="text-xs text-muted-foreground">
              {step.duration_ms}ms
            </span>
          )}
        </div>

        <h4 className="mt-1 font-medium text-sm">{step.node_name}</h4>
        <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>

        {/* Input/Output summary */}
        {hasSummary && (
          <div className="mt-2 space-y-1 rounded bg-muted/50 p-2 text-xs">
            {inputSummary && (
              <div>
                <span className="font-medium">Input: </span>
                <span className="text-muted-foreground">{inputSummary}</span>
              </div>
            )}
            {outputSummary && (
              <div>
                <span className="font-medium">Output: </span>
                <span className="text-muted-foreground">{outputSummary}</span>
              </div>
            )}
          </div>
        )}

        {/* Query Decomposition Hops (Multi-hop 쿼리 분해 단계) */}
        {step.step_type === 'decomposition' && step.details?.hops && Array.isArray(step.details.hops) && step.details.hops.length > 0 && (
          <div className="mt-3 space-y-2">
            <div className="text-xs font-medium text-muted-foreground">Query Hops:</div>
            <div className="space-y-2">
              {(step.details.hops as Array<{ step?: number; description?: string; node_label?: string; relationship?: string; direction?: string }>).map((hop, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-2 rounded border border-border bg-background p-2"
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-purple-500/20 text-xs font-bold text-purple-500">
                    {hop.step || idx + 1}
                  </span>
                  <div className="flex-1 text-xs">
                    <div className="font-medium">{hop.description || `Hop ${idx + 1}`}</div>
                    {(hop.node_label || hop.relationship) && (
                      <div className="mt-1 flex flex-wrap gap-1 text-muted-foreground">
                        {hop.node_label && (
                          <span className="rounded bg-secondary px-1.5 py-0.5">
                            :{hop.node_label}
                          </span>
                        )}
                        {hop.relationship && (
                          <span className="rounded bg-secondary px-1.5 py-0.5">
                            [{hop.relationship}]
                          </span>
                        )}
                        {hop.direction && (
                          <span className="text-muted-foreground">
                            ({hop.direction})
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {Boolean(step.details.explanation) && (
              <div className="mt-2 text-xs text-muted-foreground italic">
                {String(step.details.explanation)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default StepItem;
