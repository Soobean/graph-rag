/** Label-based color mapping for graph nodes.
 *  Shared between BaseNode (Tailwind classes) and GraphViewer (MiniMap hex colors).
 */

/** Extract a stable label key from nodeLabel (e.g. "Employee" → "employee") */
export function getLabelKey(nodeLabel?: string): string {
  return (nodeLabel ?? '').toLowerCase();
}

export const labelStyles: Record<string, { border: string; badge: string; icon: string }> = {
  employee:    { border: 'border-emerald-200 bg-white ring-emerald-100', badge: 'bg-emerald-500', icon: 'E' },
  skill:       { border: 'border-blue-200 bg-white ring-blue-100',       badge: 'bg-blue-500',    icon: 'S' },
  project:     { border: 'border-violet-200 bg-white ring-violet-100',   badge: 'bg-violet-500',  icon: 'P' },
  department:  { border: 'border-amber-200 bg-white ring-amber-100',     badge: 'bg-amber-500',   icon: 'D' },
  office:      { border: 'border-rose-200 bg-white ring-rose-100',       badge: 'bg-rose-500',    icon: 'O' },
  certificate: { border: 'border-orange-200 bg-white ring-orange-100',   badge: 'bg-orange-500',  icon: 'C' },
  concept:     { border: 'border-cyan-200 bg-white ring-cyan-100',       badge: 'bg-cyan-500',    icon: 'Co' },
};

export const defaultLabelStyle = { border: 'border-gray-200 bg-white ring-gray-100', badge: 'bg-gray-500', icon: '?' };

/** Hex colors per label for MiniMap nodeColor */
export const labelMiniMapColors: Record<string, string> = {
  employee:    '#10b981',
  skill:       '#3b82f6',
  project:     '#8b5cf6',
  department:  '#f59e0b',
  office:      '#f43f5e',
  certificate: '#f97316',
  concept:     '#06b6d4',
};

const defaultMiniMapColor = '#6b7280';

export function getMiniMapColor(nodeLabel?: string): string {
  return labelMiniMapColors[getLabelKey(nodeLabel)] ?? defaultMiniMapColor;
}
