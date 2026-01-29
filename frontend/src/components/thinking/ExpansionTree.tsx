import { ChevronRight, Circle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ConceptExpansionTree as ConceptExpansionTreeType } from '@/types/api';

interface ExpansionTreeProps {
  tree: ConceptExpansionTreeType;
  className?: string;
}

const strategyColors = {
  strict: 'border-red-200 bg-red-50',
  normal: 'border-amber-200 bg-amber-50',
  broad: 'border-green-200 bg-green-50',
};

export function ExpansionTree({ tree, className }: ExpansionTreeProps) {
  return (
    <div className={cn('rounded-lg border p-3', strategyColors[tree.expansion_strategy], className)}>
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="rounded bg-white/80 px-2 py-1">
          <span className="text-sm font-semibold">{tree.original_concept}</span>
        </div>
        <span className="text-xs text-muted-foreground">({tree.entity_type})</span>
        <span className="ml-auto rounded bg-white/80 px-1.5 py-0.5 text-xs capitalize">
          {tree.expansion_strategy}
        </span>
      </div>

      {/* Expanded concepts */}
      {tree.expanded_concepts.length > 0 && (
        <div className="mt-3 space-y-1">
          <span className="text-xs font-medium text-muted-foreground">
            Expanded to:
          </span>
          <div className="flex flex-wrap gap-1">
            {tree.expanded_concepts.map((concept, idx) => (
              <span
                key={idx}
                className="inline-flex items-center rounded bg-white/80 px-2 py-0.5 text-xs"
              >
                {concept}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Expansion path */}
      {tree.expansion_path.length > 0 && (
        <div className="mt-3 space-y-1">
          <span className="text-xs font-medium text-muted-foreground">
            Expansion path:
          </span>
          <div className="space-y-1">
            {tree.expansion_path.map((path, idx) => (
              <div key={idx} className="flex items-center gap-1 text-xs">
                <Circle className="h-2 w-2 fill-current" />
                <span>{path.from}</span>
                <ChevronRight className="h-3 w-3 text-muted-foreground" />
                <span className="text-muted-foreground">{path.relation}</span>
                <ChevronRight className="h-3 w-3 text-muted-foreground" />
                <span>{path.to}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default ExpansionTree;
