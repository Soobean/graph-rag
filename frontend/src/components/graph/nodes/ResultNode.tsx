import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import { BaseNode } from './BaseNode';
import type { FlowNode } from '@/types/graph';

function ResultNodeComponent({ id, data, selected }: NodeProps<FlowNode>) {
  return <BaseNode id={id} data={data} selected={selected} variant="result" />;
}

export const ResultNode = memo(ResultNodeComponent);
export default ResultNode;
