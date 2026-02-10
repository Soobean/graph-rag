import { Badge } from '@/components/ui/badge';
import { AlertTriangle, Link2Off, Database } from 'lucide-react';
import type { NodeDeletionImpactResponse } from '@/types/graphEdit';

interface DeletionImpactPreviewProps {
  impact: NodeDeletionImpactResponse;
}

const MAX_DISPLAY_RELATIONSHIPS = 10;

export function DeletionImpactPreview({ impact }: DeletionImpactPreviewProps) {
  const displayRelationships = impact.affected_relationships.slice(0, MAX_DISPLAY_RELATIONSHIPS);
  const remainingCount = impact.affected_relationships.length - MAX_DISPLAY_RELATIONSHIPS;

  return (
    <div className="space-y-4">
      {/* Summary Banner */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600 shrink-0" />
          <p className="text-sm text-amber-800">{impact.summary}</p>
        </div>
      </div>

      {/* Relationship Count */}
      {impact.relationship_count > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-medium">Affected Relationships</h4>
            <Badge variant="secondary">{impact.relationship_count}</Badge>
          </div>
          <div className="rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-3 py-2 text-left font-medium">Type</th>
                  <th className="px-3 py-2 text-left font-medium">Direction</th>
                  <th className="px-3 py-2 text-left font-medium">Connected Node</th>
                </tr>
              </thead>
              <tbody>
                {displayRelationships.map((rel) => (
                  <tr key={rel.id} className="border-b last:border-b-0">
                    <td className="px-3 py-2">
                      <Badge variant="outline">{rel.type}</Badge>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {rel.direction === 'outgoing' ? '\u2192' : '\u2190'}
                    </td>
                    <td className="px-3 py-2">
                      <span className="font-medium">{rel.connected_node_name}</span>
                      <span className="ml-2 text-muted-foreground">
                        ({rel.connected_node_labels.join(', ')})
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {remainingCount > 0 && (
              <p className="px-3 py-2 text-sm text-muted-foreground border-t">
                ... and {remainingCount} more relationship{remainingCount !== 1 ? 's' : ''}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Concept Bridge Impact */}
      {impact.concept_bridge && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Link2Off className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-medium">Skill-Concept Bridge</h4>
          </div>
          <div
            className={`rounded-lg border p-3 ${
              impact.concept_bridge.will_break
                ? 'border-red-200 bg-red-50'
                : 'border-border bg-muted/30'
            }`}
          >
            {impact.concept_bridge.current_concept ? (
              <div className="space-y-1 text-sm">
                <p>
                  <span className="text-muted-foreground">Current concept:</span>{' '}
                  <span className="font-medium">{impact.concept_bridge.current_concept}</span>
                </p>
                {impact.concept_bridge.current_hierarchy.length > 0 && (
                  <p className="text-muted-foreground">
                    Hierarchy: {impact.concept_bridge.current_hierarchy.join(' > ')}
                  </p>
                )}
                {impact.concept_bridge.will_break && (
                  <p className="mt-2 font-medium text-red-700">
                    This bridge will be broken by deletion
                  </p>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No matching concept found</p>
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
