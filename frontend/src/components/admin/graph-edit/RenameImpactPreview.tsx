import { Badge } from '@/components/ui/badge';
import { AlertTriangle, Link2Off, Database, ArrowRight } from 'lucide-react';
import type { RenameImpactResponse } from '@/types/graphEdit';

interface RenameImpactPreviewProps {
  impact: RenameImpactResponse;
}

export function RenameImpactPreview({ impact }: RenameImpactPreviewProps) {
  return (
    <div className="space-y-3">
      {/* Duplicate Warning */}
      {impact.has_duplicate && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 text-red-600 shrink-0" />
            <p className="text-sm text-red-800">
              A node with name &quot;{impact.new_name}&quot; already exists with the same label. This rename will create a duplicate.
            </p>
          </div>
        </div>
      )}

      {/* Summary */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600 shrink-0" />
          <p className="text-sm text-amber-800">{impact.summary}</p>
        </div>
      </div>

      {/* Concept Bridge Changes */}
      {impact.concept_bridge && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Link2Off className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-medium">Concept Bridge Change</h4>
          </div>
          <div
            className={`rounded-lg border p-3 ${
              impact.concept_bridge.will_break
                ? 'border-red-200 bg-red-50'
                : 'border-border bg-muted/30'
            }`}
          >
            <div className="flex items-center gap-3 text-sm">
              <div className="space-y-1">
                <p className="text-muted-foreground">Current</p>
                <p className="font-medium">
                  {impact.concept_bridge.current_concept || 'None'}
                </p>
                {impact.concept_bridge.current_hierarchy.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {impact.concept_bridge.current_hierarchy.join(' > ')}
                  </p>
                )}
              </div>
              <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
              <div className="space-y-1">
                <p className="text-muted-foreground">New</p>
                <p className="font-medium">
                  {impact.concept_bridge.new_concept || 'None'}
                </p>
                {impact.concept_bridge.new_hierarchy && impact.concept_bridge.new_hierarchy.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {impact.concept_bridge.new_hierarchy.join(' > ')}
                  </p>
                )}
              </div>
            </div>
            {impact.concept_bridge.will_break && (
              <p className="mt-2 text-sm font-medium text-red-700">
                This rename will break the concept bridge
              </p>
            )}
          </div>
        </div>
      )}

      {/* Downstream Effects */}
      {impact.downstream_effects.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-medium">Downstream Effects</h4>
          </div>
          <div className="space-y-2">
            {impact.downstream_effects.map((effect, idx) => (
              <div key={idx} className="rounded-lg border p-3 text-sm">
                <Badge variant="outline" className="mb-1">
                  {effect.system}
                </Badge>
                <p className="text-muted-foreground">{effect.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
