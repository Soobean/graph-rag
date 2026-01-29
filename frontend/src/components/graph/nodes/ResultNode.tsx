import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import { BaseNode } from './BaseNode';
import type { FlowNode } from '@/types/graph';

function ResultNodeComponent({ data, selected }: NodeProps<FlowNode>) {
  return <BaseNode data={data} selected={selected} variant="result" />;
}

export const ResultNode = memo(ResultNodeComponent);
export default ResultNode;
