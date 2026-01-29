import { useCallback, useMemo, useEffect } from 'react';
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  useReactFlow,
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
import { DEFAULT_LAYOUT_CONFIG } from '@/types/graph';

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

// Hop 컬럼 배경 및 헤더 컴포넌트
function HopColumns({ nodes }: { nodes: FlowNode[] }) {
  const { getViewport } = useReactFlow();
  const viewport = getViewport();

  // 노드들의 depth 값 수집
  const depths = useMemo(() => {
    const depthSet = new Set<number>();
    nodes.forEach(node => {
      const depth = node.data?.depth ?? 0;
      depthSet.add(depth);
    });
    return Array.from(depthSet).sort((a, b) => a - b);
  }, [nodes]);

  if (depths.length === 0) return null;

  const { depthSpacing } = DEFAULT_LAYOUT_CONFIG;
  const columnWidth = depthSpacing;

  return (
    <div
      className="absolute inset-0 pointer-events-none overflow-hidden"
      style={{ zIndex: 0 }}
    >
      {/* 컬럼 배경 및 헤더 */}
      <div
        className="absolute flex"
        style={{
          transform: `translate(${viewport.x}px, 0) scale(${viewport.zoom})`,
          transformOrigin: '0 0',
        }}
      >
        {depths.map((depth, index) => (
          <div
            key={depth}
            className="flex flex-col items-center"
            style={{
              width: columnWidth,
              marginLeft: index === 0 ? -columnWidth / 2 : 0,
            }}
          >
            {/* 컬럼 헤더 */}
            <div
              className="sticky top-0 z-10 px-4 py-2 rounded-b-lg bg-slate-800/90 text-white text-sm font-semibold shadow-lg"
              style={{
                transform: `scale(${1 / viewport.zoom})`,
                transformOrigin: 'top center',
              }}
            >
              Hop {depth + 1}
            </div>
            {/* 컬럼 구분선 */}
            <div
              className="h-[2000px] border-r border-dashed border-slate-300/30"
              style={{ marginTop: 8 }}
            />
          </div>
        ))}
      </div>
    </div>
  );
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
