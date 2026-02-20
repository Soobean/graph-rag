import { memo } from 'react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@xyflow/react';
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
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
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
          strokeWidth: 1.5,
          stroke: '#d1d5db',
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
          markerWidth="5"
          markerHeight="5"
          orient="auto-start-reverse"
        >
          <path
            d="M 0 0 L 10 5 L 0 10 z"
            fill="#d1d5db"
          />
        </marker>
      </defs>
      {/* Edge label */}
      {edgeData?.relationLabel && (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-auto absolute rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500"
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
