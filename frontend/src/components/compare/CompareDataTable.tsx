import { useMemo } from 'react';
import { Lock } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';
import { formatKRW, formatRate } from '@/lib/formatters';
import type { StreamingMetadata, GraphNode, GraphEdge } from '@/types/api';

const ROLE_LABELS = ['admin', 'manager', 'editor', 'viewer'] as const;

const ROLE_HEADER_COLORS = [
  'text-red-700 bg-red-50',
  'text-blue-700 bg-blue-50',
  'text-green-700 bg-green-50',
  'text-gray-700 bg-gray-50',
];

/** Properties that are access-controlled (sensitive data) */
const SENSITIVE_PROPS: Record<string, string[]> = {
  Employee: ['hourly_rate'],
  Project: ['budget_allocated', 'budget_spent'],
};

/** Edge types with sensitive properties */
const SENSITIVE_EDGE_PROPS: Record<string, string[]> = {
  HAS_SKILL: ['effective_rate'],
};

type CellStatus = { kind: 'value'; value: unknown } | { kind: 'masked' } | { kind: 'absent' };

interface ComparisonRow {
  name: string;
  label: string;
  commonProps: Record<string, unknown>;
  sensitiveProps: {
    key: string;
    cells: CellStatus[];  // per role [admin, manager, editor, viewer]
  }[];
}

interface ComparisonSummary {
  resultCounts: (number | null)[];
  nodeCounts: Record<string, (number | null)[]>;
  edgeDiffs: { label: string; counts: (number | 'masked')[] }[];
}

interface CompareDataTableProps {
  metadataByRole: (StreamingMetadata | null)[];
  isComplete: boolean;
}

// ─── Data extraction helpers ───

function getNodesByLabel(metadata: StreamingMetadata | null, label: string): GraphNode[] {
  if (!metadata?.graph_data) return [];
  return metadata.graph_data.nodes.filter((n) => n.label === label);
}

function getEdgesByLabel(metadata: StreamingMetadata | null, label: string): GraphEdge[] {
  if (!metadata?.graph_data) return [];
  return metadata.graph_data.edges.filter((e) => e.label === label);
}

function findNodeByName(nodes: GraphNode[], name: string): GraphNode | undefined {
  return nodes.find((n) => n.name.toLowerCase() === name.toLowerCase());
}

// ─── Build comparison data ───

function buildComparisonRows(metadataByRole: (StreamingMetadata | null)[]): ComparisonRow[] {
  const adminMeta = metadataByRole[0];
  if (!adminMeta?.graph_data) return [];

  const rows: ComparisonRow[] = [];

  for (const [label, sensitiveKeys] of Object.entries(SENSITIVE_PROPS)) {
    const adminNodes = getNodesByLabel(adminMeta, label);
    // Deduplicate by name (take first occurrence)
    const seen = new Set<string>();
    const uniqueAdminNodes = adminNodes.filter((n) => {
      const key = n.name.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    for (const adminNode of uniqueAdminNodes) {
      // Check if any sensitive prop actually exists in admin data
      const hasSensitive = sensitiveKeys.some((k) => k in adminNode.properties);
      if (!hasSensitive) continue;

      const commonProps: Record<string, unknown> = {};
      if ('job_type' in adminNode.properties) commonProps['job_type'] = adminNode.properties.job_type;
      if ('status' in adminNode.properties) commonProps['status'] = adminNode.properties.status;
      if ('type' in adminNode.properties) commonProps['type'] = adminNode.properties.type;

      const sensitiveProps = sensitiveKeys
        .filter((k) => k in adminNode.properties)
        .map((key) => {
          const cells: CellStatus[] = metadataByRole.map((meta) => {
            if (!meta?.graph_data) return { kind: 'absent' as const };
            const roleNodes = getNodesByLabel(meta, label);
            const match = findNodeByName(roleNodes, adminNode.name);
            if (!match) return { kind: 'absent' as const };
            if (key in match.properties) return { kind: 'value' as const, value: match.properties[key] };
            return { kind: 'masked' as const };
          });
          return { key, cells };
        });

      if (sensitiveProps.length > 0) {
        rows.push({
          name: adminNode.name,
          label,
          commonProps,
          sensitiveProps,
        });
      }
    }
  }

  return rows;
}

function buildEdgeDiffs(metadataByRole: (StreamingMetadata | null)[]): ComparisonSummary['edgeDiffs'] {
  const adminMeta = metadataByRole[0];
  if (!adminMeta?.graph_data) return [];

  const edgeLabels = new Set<string>();
  for (const label of Object.keys(SENSITIVE_EDGE_PROPS)) {
    if (adminMeta.graph_data.edges.some((e) => e.label === label)) {
      edgeLabels.add(label);
    }
  }
  // Also check MENTORS (relationship-level access control, not property-level)
  if (adminMeta.graph_data.edges.some((e) => e.label === 'MENTORS')) {
    edgeLabels.add('MENTORS');
  }

  return Array.from(edgeLabels).map((label) => {
    const adminEdges = getEdgesByLabel(adminMeta, label);
    const counts = metadataByRole.map((meta, idx): number | 'masked' => {
      if (!meta?.graph_data) return 'masked';
      const edges = getEdgesByLabel(meta, label);
      // admin (idx 0) always returns a number
      if (idx === 0) return edges.length;
      // Other roles: admin has edges but this role doesn't → masked
      if (edges.length === 0 && adminEdges.length > 0) return 'masked';
      return edges.length;
    });
    return { label, counts };
  });
}

function buildSummary(metadataByRole: (StreamingMetadata | null)[]): ComparisonSummary {
  const resultCounts = metadataByRole.map((m) => m?.result_count ?? null);

  const nodeCounts: Record<string, (number | null)[]> = {};
  const adminMeta = metadataByRole[0];
  if (adminMeta?.graph_data) {
    const labels = new Set(adminMeta.graph_data.nodes.map((n) => n.label));
    for (const label of labels) {
      nodeCounts[label] = metadataByRole.map((meta) => {
        if (!meta?.graph_data) return null;
        return meta.graph_data.nodes.filter((n) => n.label === label).length;
      });
    }
  }

  const edgeDiffs = buildEdgeDiffs(metadataByRole);

  return { resultCounts, nodeCounts, edgeDiffs };
}

// ─── Cell rendering ───

function formatValue(key: string, value: unknown): string {
  if (value == null) return '-';
  if (typeof value !== 'number') return String(value);
  // budget_allocated/budget_spent are stored in won (원) in graph_data
  if (key.includes('budget')) return formatKRW(value);
  if (key.includes('rate')) return formatRate(value);
  return String(value);
}

function MaskedCell({ reason }: { reason: 'filtered' | 'scoped' }) {
  if (reason === 'scoped') {
    return <span className="text-gray-300">&mdash;</span>;
  }
  return (
    <span className="inline-flex items-center gap-1 text-red-300 bg-red-50 px-1.5 py-0.5 rounded text-xs">
      <Lock className="h-3 w-3" />
      ████
    </span>
  );
}

function DataCell({ status, propKey }: { status: CellStatus; propKey: string }) {
  if (status.kind === 'absent') return <MaskedCell reason="scoped" />;
  if (status.kind === 'masked') return <MaskedCell reason="filtered" />;
  return <span className="text-xs font-medium">{formatValue(propKey, status.value)}</span>;
}

// ─── Skeleton ───

function SkeletonTable() {
  return (
    <div className="space-y-2 animate-pulse">
      <div className="h-4 w-48 bg-muted rounded" />
      <div className="h-32 w-full bg-muted/50 rounded" />
    </div>
  );
}

// ─── Subcomponents ───

function EntityTable({ rows, label }: { rows: ComparisonRow[]; label: string }) {
  if (rows.length === 0) return null;

  const MAX_ROWS = 10;
  const displayRows = rows.slice(0, MAX_ROWS);
  const remaining = rows.length - MAX_ROWS;

  // Collect all unique common/sensitive prop keys across ALL rows (union)
  const commonKeys = Array.from(
    new Set(displayRows.flatMap((r) => Object.keys(r.commonProps)))
  );
  const sensitiveKeys = Array.from(
    new Set(rows.flatMap((r) => r.sensitiveProps.map((p) => p.key)))
  );

  return (
    <div className="rounded-lg border">
      <div className="px-3 py-2 border-b bg-muted/30">
        <span className="text-sm font-semibold">{label}</span>
        <span className="ml-2 text-xs text-muted-foreground">{rows.length}건</span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="h-9 px-3 text-xs">Name</TableHead>
            {commonKeys.map((k) => (
              <TableHead key={k} className="h-9 px-3 text-xs">{k}</TableHead>
            ))}
            {sensitiveKeys.map((key) => (
              ROLE_LABELS.map((role, ri) => (
                <TableHead
                  key={`${key}-${role}`}
                  className={cn('h-9 px-2 text-xs text-center', ROLE_HEADER_COLORS[ri])}
                >
                  <div className="flex flex-col items-center leading-tight">
                    <span>{role}</span>
                    <span className="text-[10px] opacity-70">{key}</span>
                  </div>
                </TableHead>
              ))
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {displayRows.map((row, rowIdx) => (
            <TableRow key={`${row.label}-${row.name}-${rowIdx}`}>
              <TableCell className="px-3 py-2 text-xs font-medium">{row.name}</TableCell>
              {commonKeys.map((k) => (
                <TableCell key={k} className="px-3 py-2 text-xs">
                  {String(row.commonProps[k] ?? '')}
                </TableCell>
              ))}
              {sensitiveKeys.map((key) => {
                const prop = row.sensitiveProps.find((p) => p.key === key);
                return ROLE_LABELS.map((_role, ri) => (
                  <TableCell key={`${key}-${ri}`} className="px-2 py-2 text-center">
                    {prop ? (
                      <DataCell status={prop.cells[ri]} propKey={key} />
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </TableCell>
                ));
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {remaining > 0 && (
        <div className="px-3 py-1.5 text-xs text-muted-foreground border-t">
          외 {remaining}건
        </div>
      )}
    </div>
  );
}

function SummaryTable({ summary }: { summary: ComparisonSummary }) {
  return (
    <div className="rounded-lg border">
      <div className="px-3 py-2 border-b bg-muted/30">
        <span className="text-sm font-semibold">Summary</span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="h-9 px-3 text-xs">Metric</TableHead>
            {ROLE_LABELS.map((role, ri) => (
              <TableHead
                key={role}
                className={cn('h-9 px-3 text-xs text-center', ROLE_HEADER_COLORS[ri])}
              >
                {role}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {/* Result count row */}
          <TableRow>
            <TableCell className="px-3 py-2 text-xs font-medium">결과 수</TableCell>
            {summary.resultCounts.map((count, ri) => (
              <TableCell key={ri} className="px-3 py-2 text-xs text-center">
                {count != null ? (
                  <span className={cn('font-medium', count === 0 && 'text-red-600')}>
                    {count}
                  </span>
                ) : (
                  <span className="text-gray-300">&mdash;</span>
                )}
              </TableCell>
            ))}
          </TableRow>

          {/* Node counts per label */}
          {Object.entries(summary.nodeCounts).map(([label, counts]) => (
            <TableRow key={label}>
              <TableCell className="px-3 py-2 text-xs font-medium">{label} 노드</TableCell>
              {counts.map((count, ri) => (
                <TableCell key={ri} className="px-3 py-2 text-xs text-center">
                  {count != null ? (
                    <span className="font-medium">{count}</span>
                  ) : (
                    <span className="text-gray-300">&mdash;</span>
                  )}
                </TableCell>
              ))}
            </TableRow>
          ))}

          {/* Edge diffs */}
          {summary.edgeDiffs.map(({ label, counts }) => (
            <TableRow key={label}>
              <TableCell className="px-3 py-2 text-xs font-medium">{label} 관계</TableCell>
              {counts.map((count, ri) => (
                <TableCell key={ri} className="px-3 py-2 text-xs text-center">
                  {count === 'masked' ? (
                    <MaskedCell reason="filtered" />
                  ) : (
                    <span className="font-medium">{count}</span>
                  )}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ─── Main component ───

export function CompareDataTable({ metadataByRole, isComplete }: CompareDataTableProps) {
  const rows = useMemo(() => buildComparisonRows(metadataByRole), [metadataByRole]);
  const summary = useMemo(() => buildSummary(metadataByRole), [metadataByRole]);

  if (!isComplete) {
    return <SkeletonTable />;
  }

  // Don't render if admin has no graph_data
  if (!metadataByRole[0]?.graph_data) return null;

  // Group rows by label
  const rowsByLabel = new Map<string, ComparisonRow[]>();
  for (const row of rows) {
    const existing = rowsByLabel.get(row.label) ?? [];
    existing.push(row);
    rowsByLabel.set(row.label, existing);
  }

  const hasEntityDiff = rows.length > 0;
  const hasSummaryDiff = summary.edgeDiffs.length > 0 ||
    summary.resultCounts.some((c, i) => c !== summary.resultCounts[0] && c != null && i > 0);

  if (!hasEntityDiff && !hasSummaryDiff) return null;

  return (
    <div className="space-y-4 mb-6">
      <h2 className="text-sm font-bold text-muted-foreground uppercase tracking-wider">
        Data Comparison
      </h2>

      {Array.from(rowsByLabel.entries()).map(([label, labelRows]) => (
        <EntityTable key={label} label={label} rows={labelRows} />
      ))}

      <SummaryTable summary={summary} />
    </div>
  );
}
