import { useCallback, useMemo, useEffect } from 'react';
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  type NodeMouseHandler,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { QueryNode, ExpandedNode, ResultNode } from './nodes';
import { AnimatedEdge } from './edges';
import { NodeDetailPanel } from './NodeDetailPanel';
import { useGraphStore } from '@/stores';
import { cn } from '@/lib/utils';
import type { FlowNode, FlowEdge } from '@/types/graph';

const nodeTypes = {
  query: QueryNode,
  expanded: ExpandedNode,
  result: ResultNode,
};

const edgeTypes = {
  animated: AnimatedEdge,
};

interface GraphViewerProps {
  className?: string;
}

function GraphViewerInner({ className }: GraphViewerProps) {
  const { nodes: storeNodes, edges: storeEdges, selectNode } = useGraphStore();

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>(storeNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<FlowEdge>(storeEdges);

  // Store 변경 시 로컬 상태 동기화
  useEffect(() => {
    setNodes(storeNodes);
  }, [storeNodes, setNodes]);

  useEffect(() => {
    setEdges(storeEdges);
  }, [storeEdges, setEdges]);

  const handleNodeClick: NodeMouseHandler<FlowNode> = useCallback(
    (_event, node) => {
      selectNode(node.id);
    },
    [selectNode]
  );

  const handlePaneClick = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

  const defaultEdgeOptions = useMemo(
    () => ({
      type: 'animated',
      animated: false,
    }),
    []
  );

  // 최대 depth 계산
  const maxDepth = useMemo(() => {
    return Math.max(...nodes.map(n => n.data?.depth ?? 0), 0);
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <div className={cn('flex h-full items-center justify-center bg-muted/20', className)}>
        <div className="text-center text-muted-foreground">
          <p className="text-lg font-medium">No Graph Data</p>
          <p className="text-sm mt-2">질문을 입력하면 그래프가 표시됩니다.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('relative h-full w-full', className)}>
      {/* Hop 헤더 (고정) */}
      <div className="absolute top-0 left-0 right-0 z-20 flex justify-center gap-4 py-2 bg-gradient-to-b from-background via-background/80 to-transparent">
        {Array.from({ length: maxDepth + 1 }, (_, i) => (
          <div
            key={i}
            className="px-4 py-1.5 rounded-full bg-slate-800 text-white text-xs font-semibold shadow-md"
          >
            Hop {i + 1}
          </div>
        ))}
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.1}
        maxZoom={2}
      >
        <Controls />
        <MiniMap
          nodeStrokeWidth={3}
          zoomable
          pannable
        />
        <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
      </ReactFlow>
      <NodeDetailPanel />
    </div>
  );
}

export function GraphViewer({ className }: GraphViewerProps) {
  return (
    <ReactFlowProvider>
      <GraphViewerInner className={className} />
    </ReactFlowProvider>
  );
}

export default GraphViewer;
