import { Handle, Position } from '@xyflow/react';
import { cn } from '@/lib/utils';
import { useGraphStore } from '@/stores';
import type { FlowNodeData } from '@/types/graph';

interface BaseNodeProps {
  id: string;
  data: FlowNodeData;
  selected?: boolean;
  variant: 'query' | 'expanded' | 'result';
}

const variantStyles = {
  query: 'border-blue-200 bg-white ring-blue-100',
  expanded: 'border-amber-200 bg-white ring-amber-100',
  result: 'border-emerald-200 bg-white ring-emerald-100',
};

const variantBadgeStyles = {
  query: 'bg-blue-500',
  expanded: 'bg-amber-500',
  result: 'bg-emerald-500',
};

const variantIcons = {
  query: 'Q',
  expanded: 'E',
  result: 'R',
};

export function BaseNode({ id, data, selected, variant }: BaseNodeProps) {
  const expandNode = useGraphStore((s) => s.expandNode);

  return (
    <div
      className={cn(
        'relative min-w-[180px] max-w-[240px] rounded-xl border px-3 py-2.5',
        'shadow-sm hover:shadow-md transition-shadow duration-200',
        variantStyles[variant],
        selected && 'ring-2 shadow-md',
        data.isSelected && 'ring-2 ring-primary/40 shadow-md',
        data.isNew && 'animate-in fade-in-0 zoom-in-90 duration-500'
      )}
    >
      {/* Left Handle */}
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !border-[1.5px] !border-gray-200 !bg-white"
      />

      {/* Node Content */}
      <div className="flex items-center gap-2.5">
        {/* Icon/Badge */}
        <div
          className={cn(
            'flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold text-white',
            variantBadgeStyles[variant]
          )}
        >
          {variantIcons[variant]}
        </div>

        {/* Text Content */}
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-gray-800">
            {data.name || data.label}
          </div>
          <div className="truncate text-[11px] font-medium text-gray-400">
            {data.nodeLabel}
          </div>
        </div>
      </div>

      {/* Hidden count badge — 우측 상단 원형 뱃지 */}
      {data.hiddenCount != null && data.hiddenCount > 0 && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            expandNode(id);
          }}
          className={cn(
            'absolute -top-2.5 -right-2.5 z-10',
            'flex h-5 min-w-5 items-center justify-center rounded-full px-1',
            'bg-red-500',
            'text-[9px] font-bold text-white leading-none',
            'shadow-sm hover:bg-red-600 hover:scale-110',
            'transition-all cursor-pointer',
            'animate-in fade-in-0 zoom-in-75 duration-500'
          )}
        >
          +{data.hiddenCount}
        </button>
      )}

      {/* Right Handle */}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2.5 !w-2.5 !border-[1.5px] !border-gray-200 !bg-white"
      />
    </div>
  );
}

export default BaseNode;
