import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
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
import { GitBranchPlus, CirclePlus } from 'lucide-react';

import { QueryNode, ExpandedNode, ResultNode } from './nodes';
import { AnimatedEdge } from './edges';
import { NodeDetailPanel } from './NodeDetailPanel';
import { ResultTable } from './ResultTable';
import { CreateNodeDialog } from '@/components/admin/graph-edit/CreateNodeDialog';
import { CreateEdgeDialog } from '@/components/admin/graph-edit/CreateEdgeDialog';
import { Button } from '@/components/ui/button';
import { useGraphStore } from '@/stores';
import { cn } from '@/lib/utils';
import type { FlowNode, FlowEdge } from '@/types/graph';
import type { NodeResponse } from '@/types/graphEdit';

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
  const { nodes: storeNodes, edges: storeEdges, tabularData, selectNode, addNode, addEdge, expandNode } = useGraphStore();
  const layoutVersion = useGraphStore((s) => s._layoutVersion);
  const { fitView } = useReactFlow();

  const [createNodeOpen, setCreateNodeOpen] = useState(false);
  const [createEdgeOpen, setCreateEdgeOpen] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>(storeNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<FlowEdge>(storeEdges);

  // 새 그래프 데이터 도착 시 fitView 재호출
  // CSS transition(300ms) 완료 후 resize 이벤트를 발생시켜
  // React Flow가 컨테이너 크기를 정확히 감지하게 한 뒤 fitView 실행
  useEffect(() => {
    if (storeNodes.length > 0) {
      const timer = setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
        requestAnimationFrame(() => fitView({ padding: 0.15, duration: 400, minZoom: 0.3 }));
      }, 350);
      return () => clearTimeout(timer);
    }
  }, [storeNodes, fitView]);

  // Store 변경 시 로컬 상태 동기화
  // _layoutVersion 변경(expand/new data) 시 dagre position 사용,
  // 그 외(선택 등) 기존 드래그 위치 보존
  const layoutVersionRef = useRef(layoutVersion);
  useEffect(() => {
    const isRelayout = layoutVersion !== layoutVersionRef.current;
    layoutVersionRef.current = layoutVersion;

    setNodes((currentNodes) => {
      if (isRelayout || currentNodes.length === 0) return storeNodes;
      const posMap = new Map(currentNodes.map((n) => [n.id, n.position]));
      return storeNodes.map((sn) => ({
        ...sn,
        position: posMap.get(sn.id) ?? sn.position,
      }));
    });
  }, [storeNodes, setNodes, layoutVersion]);

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

  // 더블클릭으로 숨겨진 이웃 노드 확장
  const handleNodeDoubleClick: NodeMouseHandler<FlowNode> = useCallback(
    (_event, node) => {
      expandNode(node.id);
    },
    [expandNode]
  );

  // Edge creation: add missing endpoint nodes to graph, then add the edge
  const handleEdgeCreated = useCallback(
    (
      edge: { id: string; type: string; source_id: string; target_id: string },
      sourceNode: NodeResponse,
      targetNode: NodeResponse,
    ) => {
      const existingIds = new Set(storeNodes.map((n) => n.id));
      if (!existingIds.has(sourceNode.id)) {
        addNode({ id: sourceNode.id, labels: sourceNode.labels, properties: sourceNode.properties });
      }
      if (!existingIds.has(targetNode.id)) {
        addNode({ id: targetNode.id, labels: targetNode.labels, properties: targetNode.properties });
      }
      addEdge(edge);
    },
    [storeNodes, addNode, addEdge],
  );

  const defaultEdgeOptions = useMemo(
    () => ({
      type: 'animated',
      animated: false,
    }),
    []
  );

  if (nodes.length === 0) {
    if (tabularData) {
      return <ResultTable data={tabularData} className={className} />;
    }
    return (
      <div className={cn('flex h-full items-center justify-center bg-gray-50/50', className)}>
        <div className="text-center text-muted-foreground">
          <p className="text-lg font-medium">No Graph Data</p>
          <p className="text-sm mt-2">질문을 입력하면 그래프가 표시됩니다.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('relative h-full w-full', className)}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onPaneClick={handlePaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        fitView
        fitViewOptions={{ padding: 0.15, minZoom: 0.3 }}
        minZoom={0.1}
        maxZoom={2}
      >
        <Controls className="!shadow-sm !border !border-gray-200 !rounded-lg" />
        <MiniMap
          nodeStrokeWidth={2}
          nodeColor="#e2e8f0"
          maskColor="rgba(0,0,0,0.05)"
          className="!shadow-sm !border !border-gray-200 !rounded-lg"
          zoomable
          pannable
        />
        <Background variant={BackgroundVariant.Dots} gap={20} size={0.8} color="#e2e8f0" />
      </ReactFlow>
      <NodeDetailPanel />

      {/* Create Node / Edge floating buttons */}
      <div className="absolute bottom-4 right-4 z-10 flex gap-2">
        <Button
          size="sm"
          variant="secondary"
          className="shadow-sm border border-gray-200"
          title="Create node"
          onClick={() => setCreateNodeOpen(true)}
        >
          <CirclePlus className="mr-1 h-4 w-4" />
          Node
        </Button>
        <Button
          size="sm"
          variant="secondary"
          className="shadow-sm border border-gray-200"
          title="Create edge"
          onClick={() => setCreateEdgeOpen(true)}
        >
          <GitBranchPlus className="mr-1 h-4 w-4" />
          Edge
        </Button>
      </div>

      {/* Create Dialogs */}
      <CreateNodeDialog
        open={createNodeOpen}
        onOpenChange={setCreateNodeOpen}
        onSuccess={addNode}
      />
      <CreateEdgeDialog
        open={createEdgeOpen}
        onOpenChange={setCreateEdgeOpen}
        onSuccess={handleEdgeCreated}
      />
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
