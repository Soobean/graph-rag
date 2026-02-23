import { Handle, Position } from '@xyflow/react';
import { cn } from '@/lib/utils';
import { useGraphStore } from '@/stores';
import type { FlowNodeData } from '@/types/graph';
import { getLabelKey, labelStyles, defaultLabelStyle } from './labelColors';

interface BaseNodeProps {
  id: string;
  data: FlowNodeData;
  selected?: boolean;
  variant: 'query' | 'expanded' | 'result';
}

export function BaseNode({ id, data, selected, variant }: BaseNodeProps) {
  const expandNode = useGraphStore((s) => s.expandNode);
  const style = labelStyles[getLabelKey(data.nodeLabel)] ?? defaultLabelStyle;

  return (
    <div
      className={cn(
        'relative min-w-[180px] max-w-[240px] rounded-xl border px-3 py-2.5',
        'shadow-sm hover:shadow-md transition-shadow duration-200',
        style.border,
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
            style.badge
          )}
        >
          {style.icon}
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

      {/* Query origin indicator — small dot for depth=0 nodes */}
      {variant === 'query' && (
        <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 h-1.5 w-1.5 rounded-full bg-gray-400" />
      )}

      {/* Hidden count badge */}
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
