import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import { BaseNode } from './BaseNode';
import type { FlowNode } from '@/types/graph';

function QueryNodeComponent({ id, data, selected }: NodeProps<FlowNode>) {
  return <BaseNode id={id} data={data} selected={selected} variant="query" />;
}

export const QueryNode = memo(QueryNodeComponent);
export default QueryNode;
