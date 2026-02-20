import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import { BaseNode } from './BaseNode';
import type { FlowNode } from '@/types/graph';

function ExpandedNodeComponent({ id, data, selected }: NodeProps<FlowNode>) {
  return <BaseNode id={id} data={data} selected={selected} variant="expanded" />;
}

export const ExpandedNode = memo(ExpandedNodeComponent);
export default ExpandedNode;
