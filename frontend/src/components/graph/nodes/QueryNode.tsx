import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import { BaseNode } from './BaseNode';
import type { FlowNode } from '@/types/graph';

function QueryNodeComponent({ data, selected }: NodeProps<FlowNode>) {
  return <BaseNode data={data} selected={selected} variant="query" />;
}

export const QueryNode = memo(QueryNodeComponent);
export default QueryNode;
