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

interface HopItem {
  step?: number;
  description?: string;
  node_label?: string;
  relationship?: string;
  direction?: string;
}

export function StepItem({ step, isLast = false }: StepItemProps) {
  const config = stepTypeConfig[step.step_type] || { icon: CheckCircle, color: 'text-gray-500' };
  const Icon = config.icon;

  const renderSummary = (): React.ReactNode => {
    const input = step.input_summary;
    const output = step.output_summary;
    if (!input && !output) return null;

    return (
      <div className="mt-2 space-y-1 rounded bg-muted/50 p-2 text-xs">
        {input ? (
          <div>
            <span className="font-medium">Input: </span>
            <span className="text-muted-foreground">{input}</span>
          </div>
        ) : null}
        {output ? (
          <div>
            <span className="font-medium">Output: </span>
            <span className="text-muted-foreground">{output}</span>
          </div>
        ) : null}
      </div>
    );
  };

  const renderHops = (): React.ReactNode => {
    if (step.step_type !== 'decomposition') return null;
    const hops = step.details?.hops;
    if (!hops || !Array.isArray(hops) || hops.length === 0) return null;

    const typedHops = hops as HopItem[];
    const explanation = step.details?.explanation;

    return (
      <div className="mt-3 space-y-2">
        <div className="text-xs font-medium text-muted-foreground">Query Hops:</div>
        <div className="space-y-2">
          {typedHops.map((hop, idx) => (
            <div
              key={idx}
              className="flex items-start gap-2 rounded border border-border bg-background p-2"
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-purple-500/20 text-xs font-bold text-purple-500">
                {hop.step ?? idx + 1}
              </span>
              <div className="flex-1 text-xs">
                <div className="font-medium">{hop.description ?? `Hop ${idx + 1}`}</div>
                {(hop.node_label || hop.relationship) ? (
                  <div className="mt-1 flex flex-wrap gap-1 text-muted-foreground">
                    {hop.node_label ? (
                      <span className="rounded bg-secondary px-1.5 py-0.5">
                        :{hop.node_label}
                      </span>
                    ) : null}
                    {hop.relationship ? (
                      <span className="rounded bg-secondary px-1.5 py-0.5">
                        [{hop.relationship}]
                      </span>
                    ) : null}
                    {hop.direction ? (
                      <span className="text-muted-foreground">
                        ({hop.direction})
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
        {explanation ? (
          <div className="mt-2 text-xs text-muted-foreground italic">
            {String(explanation)}
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <div className="relative flex gap-3">
      {!isLast ? (
        <div className="absolute left-4 top-10 h-full w-0.5 bg-border" />
      ) : null}

      <div
        className={cn(
          'relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-background border-2',
          config.color
        )}
        style={{ borderColor: 'currentColor' }}
      >
        <Icon className="h-4 w-4" />
      </div>

      <div className="flex-1 pb-6">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">
            Step {step.step_number}
          </span>
          <span className="rounded bg-secondary px-1.5 py-0.5 text-xs capitalize">
            {step.step_type}
          </span>
          {step.duration_ms !== undefined ? (
            <span className="text-xs text-muted-foreground">
              {step.duration_ms}ms
            </span>
          ) : null}
        </div>

        <h4 className="mt-1 font-medium text-sm">{step.node_name}</h4>
        <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>

        {renderSummary()}
        {renderHops()}
      </div>
    </div>
  );
}

export default StepItem;
