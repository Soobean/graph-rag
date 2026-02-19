import { useState, useCallback, useMemo, useEffect } from 'react';
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
  const { nodes: storeNodes, edges: storeEdges, tabularData, selectNode, addNode, addEdge } = useGraphStore();

  const [createNodeOpen, setCreateNodeOpen] = useState(false);
  const [createEdgeOpen, setCreateEdgeOpen] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>(storeNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<FlowEdge>(storeEdges);

  // Store 변경 시 로컬 상태 동기화 (기존 노드의 드래그 위치 보존)
  useEffect(() => {
    setNodes((currentNodes) => {
      if (currentNodes.length === 0) return storeNodes;
      const posMap = new Map(currentNodes.map((n) => [n.id, n.position]));
      return storeNodes.map((sn) => ({
        ...sn,
        position: posMap.get(sn.id) ?? sn.position,
      }));
    });
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

  // 최대 depth 계산
  const maxDepth = useMemo(() => {
    return Math.max(...nodes.map(n => n.data?.depth ?? 0), 0);
  }, [nodes]);

  if (nodes.length === 0) {
    if (tabularData) {
      return <ResultTable data={tabularData} className={className} />;
    }
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

      {/* Create Node / Edge floating buttons */}
      <div className="absolute bottom-4 right-4 z-10 flex gap-2">
        <Button
          size="sm"
          variant="secondary"
          className="shadow-lg"
          title="Create node"
          onClick={() => setCreateNodeOpen(true)}
        >
          <CirclePlus className="mr-1 h-4 w-4" />
          Node
        </Button>
        <Button
          size="sm"
          variant="secondary"
          className="shadow-lg"
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
