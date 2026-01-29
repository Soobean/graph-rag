import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import { BaseNode } from './BaseNode';
import type { FlowNode } from '@/types/graph';

function ExpandedNodeComponent({ data, selected }: NodeProps<FlowNode>) {
  return <BaseNode data={data} selected={selected} variant="expanded" />;
}

export const ExpandedNode = memo(ExpandedNodeComponent);
export default ExpandedNode;
