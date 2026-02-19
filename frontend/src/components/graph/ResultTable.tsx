import { useState, useMemo } from 'react';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { cn } from '@/lib/utils';
import type { TabularData } from '@/types/api';

interface ResultTableProps {
  data: TabularData;
  className?: string;
}

// ── Column header formatting ──────────────────────────────────────────

const COLUMN_LABELS: Record<string, string> = {
  // Employee / Organization
  name: '이름',
  employee_name: '직원명',
  department: '부서',
  department_name: '부서명',
  team: '팀',
  position: '직급',
  role: '역할',
  email: '이메일',

  // Skill
  skill: '스킬',
  skill_name: '스킬명',
  skills: '스킬 목록',
  proficiency: '숙련도',
  level: '레벨',

  // Project
  project: '프로젝트',
  project_name: '프로젝트명',
  status: '상태',
  start_date: '시작일',
  end_date: '종료일',

  // Aggregation
  count: '건수',
  total_count: '총 건수',
  avg_rate: '평균 단가',
  avg_cost: '평균 비용',
  total_cost: '총 비용',
  avg_experience: '평균 경력',
  employee_count: '직원 수',
  skill_count: '스킬 수',
  project_count: '프로젝트 수',
  member_count: '인원 수',
  average: '평균',
  sum: '합계',
  min: '최소',
  max: '최대',
};

function formatColumnHeader(key: string): string {
  const label = COLUMN_LABELS[key.toLowerCase()];
  if (label) return label;

  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Value formatting ──────────────────────────────────────────────────

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'number') return value.toLocaleString();
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

function isNumeric(value: unknown): boolean {
  return typeof value === 'number';
}

// ── Sorting ───────────────────────────────────────────────────────────

type SortDirection = 'asc' | 'desc' | null;

function compareValues(a: unknown, b: unknown, direction: 'asc' | 'desc'): number {
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;

  const mul = direction === 'asc' ? 1 : -1;

  if (typeof a === 'number' && typeof b === 'number') {
    return (a - b) * mul;
  }
  return String(a).localeCompare(String(b), 'ko') * mul;
}

// ── Chart configuration ───────────────────────────────────────────────

interface ChartConfig {
  categoryKey: string;
  valueKeys: string[];
}

const CHART_COLORS = [
  'hsl(221, 83%, 53%)',   // blue
  'hsl(142, 71%, 45%)',   // green
  'hsl(280, 67%, 54%)',   // purple
  'hsl(32, 95%, 53%)',    // orange
  'hsl(350, 80%, 55%)',   // rose
];

const MAX_CHART_BARS = 15;

function detectChartConfig(data: TabularData): ChartConfig | null {
  if (data.rows.length < 2) return null;

  const stringCols: string[] = [];
  const numericCols: string[] = [];

  const sample = data.rows.slice(0, 10);
  for (const col of data.columns) {
    const hasString = sample.some((r) => typeof r[col] === 'string');
    const hasNumber = sample.some((r) => typeof r[col] === 'number');

    if (hasString && !hasNumber) stringCols.push(col);
    else if (hasNumber) numericCols.push(col);
  }

  if (numericCols.length === 0 || stringCols.length === 0) return null;

  return { categoryKey: stringCols[0], valueKeys: numericCols };
}

// ── Custom chart tooltip ──────────────────────────────────────────────

interface TooltipPayloadEntry {
  color?: string;
  dataKey?: string | number;
  value?: number;
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-lg border bg-background px-3 py-2 shadow-md">
      <p className="mb-1 text-sm font-medium text-foreground">{label}</p>
      {payload.map((entry, idx) => (
        <p key={idx} className="text-xs text-muted-foreground">
          <span style={{ color: entry.color }}>&#9679;</span>{' '}
          {formatColumnHeader(String(entry.dataKey))}:{' '}
          <span className="tabular-nums font-medium text-foreground">
            {typeof entry.value === 'number'
              ? entry.value.toLocaleString()
              : entry.value}
          </span>
        </p>
      ))}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────

export function ResultTable({ data, className }: ResultTableProps) {
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);

  const chartConfig = useMemo(() => detectChartConfig(data), [data]);

  const handleSort = (col: string) => {
    if (sortColumn !== col) {
      setSortColumn(col);
      setSortDirection('asc');
    } else if (sortDirection === 'asc') {
      setSortDirection('desc');
    } else {
      setSortColumn(null);
      setSortDirection(null);
    }
  };

  const sortedRows = useMemo(() => {
    if (!sortColumn || !sortDirection) return data.rows;
    return [...data.rows].sort((a, b) =>
      compareValues(a[sortColumn], b[sortColumn], sortDirection)
    );
  }, [data.rows, sortColumn, sortDirection]);

  // Chart uses only the first N rows (unsorted, original order)
  const chartRows = useMemo(
    () => data.rows.slice(0, MAX_CHART_BARS),
    [data.rows]
  );

  const chartHeight = useMemo(() => {
    const barCount = Math.min(chartRows.length, MAX_CHART_BARS);
    return Math.max(barCount * 32 + 40, 160);
  }, [chartRows.length]);

  return (
    <div className={cn('flex h-full flex-col bg-muted/20', className)}>
      {/* Header */}
      <div className="shrink-0 border-b px-4 py-3">
        <h3 className="text-sm font-semibold text-muted-foreground">
          Query Results
          <span className="ml-2 text-xs font-normal">
            ({data.total_count}건)
          </span>
        </h3>
      </div>

      {/* Scrollable area: chart + table scroll together */}
      <div className="min-h-0 flex-1 overflow-auto">
        {/* Chart section */}
        {chartConfig && (
          <div className="border-b px-2 py-3">
            <ResponsiveContainer width="100%" height={chartHeight}>
              <BarChart
                data={chartRows}
                layout="vertical"
                margin={{ top: 4, right: 24, left: 8, bottom: 4 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  horizontal={false}
                  opacity={0.3}
                />
                <XAxis
                  type="number"
                  tick={{ fontSize: 11, fill: 'currentColor', opacity: 0.5 }}
                  tickFormatter={(v: number) => v.toLocaleString()}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey={chartConfig.categoryKey}
                  tick={{ fontSize: 12, fill: 'currentColor' }}
                  width={90}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  content={<ChartTooltip />}
                  cursor={{ fill: 'currentColor', opacity: 0.05 }}
                />
                {chartConfig.valueKeys.map((key, idx) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    fill={CHART_COLORS[idx % CHART_COLORS.length]}
                    radius={[0, 4, 4, 0]}
                    barSize={20}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
            {data.rows.length > MAX_CHART_BARS && (
              <p className="mt-1 text-center text-[11px] text-muted-foreground">
                상위 {MAX_CHART_BARS}건만 차트에 표시
              </p>
            )}
          </div>
        )}

        {/* Table section */}
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 border-b bg-muted/80 backdrop-blur-sm">
            <tr>
              {data.columns.map((col) => (
                <th
                  key={col}
                  className="h-10 px-4 text-left align-middle text-xs font-semibold
                             text-muted-foreground whitespace-nowrap cursor-pointer
                             select-none hover:text-foreground transition-colors"
                  onClick={() => handleSort(col)}
                >
                  <span className="inline-flex items-center gap-1">
                    {formatColumnHeader(col)}
                    {sortColumn === col ? (
                      sortDirection === 'asc' ? (
                        <ArrowUp className="h-3 w-3" />
                      ) : (
                        <ArrowDown className="h-3 w-3" />
                      )
                    ) : (
                      <ArrowUpDown className="h-3 w-3 opacity-30" />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, idx) => (
              <tr
                key={idx}
                className={cn(
                  'border-b transition-colors hover:bg-primary/5',
                  idx % 2 === 1 && 'bg-muted/25'
                )}
              >
                {data.columns.map((col) => (
                  <td
                    key={col}
                    className={cn(
                      'px-4 py-3 align-middle whitespace-nowrap text-sm',
                      isNumeric(row[col])
                        ? 'text-right tabular-nums font-mono'
                        : 'text-foreground'
                    )}
                  >
                    {formatValue(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      {data.has_more && (
        <div className="shrink-0 border-t px-4 py-2 text-center text-xs text-muted-foreground">
          총 {data.total_count.toLocaleString()}건 중 상위 {data.rows.length}건 표시
        </div>
      )}
    </div>
  );
}

export default ResultTable;
