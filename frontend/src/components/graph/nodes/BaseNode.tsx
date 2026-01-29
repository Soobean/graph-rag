import { Handle, Position } from '@xyflow/react';
import { cn } from '@/lib/utils';
import type { FlowNodeData } from '@/types/graph';

interface BaseNodeProps {
  data: FlowNodeData;
  selected?: boolean;
  variant: 'query' | 'expanded' | 'result';
}

const variantStyles = {
  query: 'border-blue-500 bg-blue-50 ring-blue-200',
  expanded: 'border-amber-500 bg-amber-50 ring-amber-200',
  result: 'border-emerald-500 bg-emerald-50 ring-emerald-200',
};

const variantIcons = {
  query: 'Q',
  expanded: 'E',
  result: 'R',
};

export function BaseNode({ data, selected, variant }: BaseNodeProps) {
  const nodeStyle = data.style;

  return (
    <div
      className={cn(
        'relative min-w-[140px] rounded-lg border-2 px-3 py-2 shadow-md transition-all',
        variantStyles[variant],
        selected && 'ring-2',
        data.isSelected && 'ring-2 ring-primary'
      )}
      style={{
        borderColor: nodeStyle?.color || undefined,
      }}
    >
      {/* Left Handle */}
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-2 !border-gray-300 !bg-white"
      />

      {/* Node Content */}
      <div className="flex items-start gap-2">
        {/* Icon/Badge */}
        <div
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
          style={{ backgroundColor: nodeStyle?.color || '#6b7280' }}
        >
          {variantIcons[variant]}
        </div>

        {/* Text Content */}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-gray-900">
            {data.name || data.label}
          </div>
          <div className="truncate text-xs text-gray-500">
            {data.nodeLabel}
          </div>
        </div>
      </div>

      {/* Hop indicator */}
      <div className="absolute -right-1 -top-2 flex items-center justify-center rounded-full bg-slate-800 px-1.5 py-0.5 text-[9px] font-semibold text-white shadow-sm">
        H{(data.depth ?? 0) + 1}
      </div>

      {/* Right Handle */}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-2 !border-gray-300 !bg-white"
      />
    </div>
  );
}

export default BaseNode;
