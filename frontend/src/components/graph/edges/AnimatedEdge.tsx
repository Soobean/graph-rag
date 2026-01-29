import { memo } from 'react';
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath } from '@xyflow/react';
import type { EdgeProps } from '@xyflow/react';
import type { FlowEdge, FlowEdgeData } from '@/types/graph';

function AnimatedEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  style,
}: EdgeProps<FlowEdge>) {
  // SmoothStep path for cleaner orthogonal edges
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 8,
  });

  const edgeData = data as FlowEdgeData | undefined;

  return (
    <>
      {/* Edge path with arrow marker */}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={`url(#arrow-${id})`}
        style={{
          ...style,
          strokeWidth: 2,
          stroke: '#64748b',
          strokeLinecap: 'round',
        }}
      />
      {/* Custom arrow marker */}
      <defs>
        <marker
          id={`arrow-${id}`}
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path
            d="M 0 0 L 10 5 L 0 10 z"
            fill="#64748b"
          />
        </marker>
      </defs>
      {/* Edge label */}
      {edgeData?.relationLabel && (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-auto absolute rounded-md bg-slate-700 px-2 py-1 text-xs font-medium text-white shadow-md border border-slate-600"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            }}
          >
            {edgeData.relationLabel}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const AnimatedEdge = memo(AnimatedEdgeComponent);
export default AnimatedEdge;
