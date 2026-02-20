import { create } from 'zustand';
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from 'd3-force';
import type { FlowNode, FlowEdge, LayoutConfig } from '../types/graph';
import type { ExplainableGraphData, GraphNode, GraphEdge, TabularData } from '../types/api';

// Progressive disclosure: 허브 노드의 이웃이 이 값을 초과하면 접기
const COLLAPSE_THRESHOLD = 8;
// 초기 표시할 이웃 노드 수
const INITIAL_VISIBLE = 5;

interface GraphState {
  nodes: FlowNode[];
  edges: FlowEdge[];
  selectedNodeId: string | null;
  layoutConfig: LayoutConfig;
  tabularData: TabularData | null;

  // Progressive disclosure internal state
  _rawGraphData: ExplainableGraphData | null;
  _collapsedGroups: Record<string, string[]>; // hubNodeId → hiddenNodeIds
  _layoutVersion: number; // force 재계산 추적 (expand 시 position 보존 방지)

  // Actions
  setGraphData: (data: ExplainableGraphData) => void;
  setTabularData: (data: TabularData) => void;
  selectNode: (nodeId: string | null) => void;
  getSelectedNode: () => FlowNode | null;
  clearGraph: () => void;
  updateLayoutConfig: (config: Partial<LayoutConfig>) => void;
  updateNodeData: (nodeId: string, properties: Record<string, unknown>) => void;
  removeNode: (nodeId: string) => void;
  addNode: (node: { id: string; labels: string[]; properties: Record<string, unknown> }) => void;
  addEdge: (edge: { id: string; type: string; source_id: string; target_id: string }) => void;
  expandNode: (nodeId: string) => void;
}

/**
 * d3-force 기반 Force-Directed 레이아웃 계산
 *
 * 노드들끼리 반발력(charge)으로 겹치지 않게 하고,
 * 엣지는 스프링(link force)으로 당겨서 자연스럽게 퍼지도록 배치.
 * start(depth=0) 노드는 중앙에 고정(fx/fy)하여 쿼리 엔티티가 허브 중심이 됨.
 */

interface SimNode extends SimulationNodeDatum {
  id: string;
  depth: number;
}

function calculateForceLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
): Map<string, { x: number; y: number; depth: number }> {
  if (nodes.length === 0) return new Map();

  const nodeIds = new Set(nodes.map((n) => n.id));

  // 시뮬레이션용 노드 생성
  const simNodes: SimNode[] = nodes.map((node) => {
    const depth =
      node.depth !== undefined && node.depth >= 0
        ? node.depth
        : node.role === 'start'
          ? 0
          : node.role === 'intermediate'
            ? 1
            : 2;

    const isCenter = depth === 0;
    return {
      id: node.id,
      depth,
      // start 노드는 중앙 고정, 나머지는 랜덤 초기 위치
      x: isCenter ? 0 : (Math.random() - 0.5) * 400,
      y: isCenter ? 0 : (Math.random() - 0.5) * 400,
      ...(isCenter ? { fx: 0, fy: 0 } : {}),
    };
  });

  // 시뮬레이션용 링크 (유효한 엣지만)
  const simLinks: SimulationLinkDatum<SimNode>[] = edges
    .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
    .map((e) => ({ source: e.source, target: e.target }));

  // 노드 수에 따른 동적 파라미터
  const n = nodes.length;
  const chargeStrength = n > 50 ? -300 : n > 20 ? -500 : -700;
  const linkDistance = n > 50 ? 120 : n > 20 ? 160 : 200;
  const collideRadius = n > 50 ? 60 : 80;

  // 시뮬레이션 구성
  const simulation = forceSimulation<SimNode>(simNodes)
    .force(
      'link',
      forceLink<SimNode, SimulationLinkDatum<SimNode>>(simLinks)
        .id((d) => d.id)
        .distance(linkDistance)
        .strength(0.7)
    )
    .force('charge', forceManyBody<SimNode>().strength(chargeStrength))
    .force('center', forceCenter<SimNode>(0, 0).strength(0.1))
    .force('collide', forceCollide<SimNode>(collideRadius).strength(0.8))
    .stop();

  // 동기 실행: 300 tick으로 수렴
  const tickCount = Math.min(300, Math.max(100, n * 3));
  simulation.tick(tickCount);

  // 결과 추출
  const positions = new Map<string, { x: number; y: number; depth: number }>();
  for (const node of simNodes) {
    positions.set(node.id, {
      x: node.x ?? 0,
      y: node.y ?? 0,
      depth: node.depth,
    });
  }

  return positions;
}

// API GraphNode를 React Flow FlowNode로 변환
function convertToFlowNodes(
  nodes: GraphNode[],
  positions: Map<string, { x: number; y: number; depth: number }>
): FlowNode[] {
  return nodes.map((node) => {
    const pos = positions.get(node.id) || { x: 0, y: 0, depth: 0 };
    // depth에 따라 노드 타입 결정: 0=query, 1=expanded, 2+=result
    const nodeType = pos.depth === 0 ? 'query' : pos.depth === 1 ? 'expanded' : 'result';

    return {
      id: node.id,
      type: nodeType,
      position: { x: pos.x, y: pos.y },
      data: {
        label: node.label,
        name: node.name,
        nodeLabel: node.label,
        properties: node.properties,
        role: pos.depth === 0 ? 'start' : pos.depth === 1 ? 'intermediate' : 'end',
        depth: pos.depth,
        style: node.style,
        isSelected: false,
      },
    };
  });
}

// API GraphEdge를 React Flow FlowEdge로 변환
function convertToFlowEdges(edges: GraphEdge[]): FlowEdge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: 'animated',
    animated: false,
    data: {
      relationLabel: edge.label,
      properties: edge.properties,
    },
  }));
}

/**
 * Progressive disclosure 계산
 * 허브 노드(degree > COLLAPSE_THRESHOLD)의 이웃을 INITIAL_VISIBLE개만 노출
 */
function computeProgressiveDisclosure(
  nodes: GraphNode[],
  edges: GraphEdge[]
): {
  visibleNodeIds: Set<string>;
  collapsedGroups: Record<string, string[]>;
} {
  // 양방향 인접 리스트 구성
  const neighbors = new Map<string, string[]>();
  for (const node of nodes) {
    neighbors.set(node.id, []);
  }
  for (const edge of edges) {
    neighbors.get(edge.source)?.push(edge.target);
    neighbors.get(edge.target)?.push(edge.source);
  }

  // 항상 표시할 노드 (depth 0 / start 역할)
  const forceVisible = new Set<string>();
  for (const node of nodes) {
    if (node.depth === 0 || node.role === 'start') {
      forceVisible.add(node.id);
    }
  }

  // 허브 탐색: degree > COLLAPSE_THRESHOLD
  const hubs: string[] = [];
  for (const [nodeId, nbrs] of neighbors) {
    if (nbrs.length > COLLAPSE_THRESHOLD) {
      hubs.push(nodeId);
      forceVisible.add(nodeId);
    }
  }

  // 허브 없으면 전체 표시
  if (hubs.length === 0) {
    return {
      visibleNodeIds: new Set(nodes.map((n) => n.id)),
      collapsedGroups: {},
    };
  }

  // 각 허브별로 이웃 정렬 → 상위 INITIAL_VISIBLE만 유지
  const collapsedGroups: Record<string, string[]> = {};
  for (const hubId of hubs) {
    const nbrs = neighbors.get(hubId) || [];
    // forceVisible/허브 우선, 그 다음 degree 높은 순
    const sorted = [...nbrs].sort((a, b) => {
      if (forceVisible.has(a) && !forceVisible.has(b)) return -1;
      if (!forceVisible.has(a) && forceVisible.has(b)) return 1;
      return (neighbors.get(b)?.length || 0) - (neighbors.get(a)?.length || 0);
    });

    const visible = sorted.slice(0, INITIAL_VISIBLE);
    const hidden = sorted.slice(INITIAL_VISIBLE).filter((id) => !forceVisible.has(id));

    visible.forEach((id) => forceVisible.add(id));
    if (hidden.length > 0) {
      collapsedGroups[hubId] = hidden;
    }
  }

  // 최종 visible 집합
  const allHidden = new Set(Object.values(collapsedGroups).flat());
  const visibleNodeIds = new Set<string>();
  for (const node of nodes) {
    if (!allHidden.has(node.id) || forceVisible.has(node.id)) {
      visibleNodeIds.add(node.id);
    }
  }

  // forceVisible과 겹치는 hidden 제거
  for (const [hubId, hidden] of Object.entries(collapsedGroups)) {
    collapsedGroups[hubId] = hidden.filter((id) => !visibleNodeIds.has(id));
    if (collapsedGroups[hubId].length === 0) delete collapsedGroups[hubId];
  }

  return { visibleNodeIds, collapsedGroups };
}

const defaultLayoutConfig: LayoutConfig = {
  direction: 'LR',
  nodeSpacingY: 80,
  depthSpacing: 280,
};

export const useGraphStore = create<GraphState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  layoutConfig: defaultLayoutConfig,
  tabularData: null,
  _rawGraphData: null,
  _collapsedGroups: {},
  _layoutVersion: 0,

  setGraphData: (data: ExplainableGraphData) => {
    // Progressive disclosure 적용
    const { visibleNodeIds, collapsedGroups } = computeProgressiveDisclosure(
      data.nodes,
      data.edges
    );


    const visibleNodes = data.nodes.filter((n) => visibleNodeIds.has(n.id));
    const visibleEdges = data.edges.filter(
      (e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)
    );

    const positions = calculateForceLayout(visibleNodes, visibleEdges);
    const flowNodes = convertToFlowNodes(visibleNodes, positions);
    const flowEdges = convertToFlowEdges(visibleEdges);

    // 허브 노드에 hiddenCount 주입
    for (const node of flowNodes) {
      const hidden = collapsedGroups[node.id];
      if (hidden && hidden.length > 0) {
        node.data = { ...node.data, hiddenCount: hidden.length };
      }
    }

    set({
      nodes: flowNodes,
      edges: flowEdges,
      tabularData: null,
      _rawGraphData: data,
      _collapsedGroups: collapsedGroups,
      _layoutVersion: get()._layoutVersion + 1,
    });
  },

  setTabularData: (data: TabularData) => {
    set({
      nodes: [],
      edges: [],
      selectedNodeId: null,
      tabularData: data,
    });
  },

  selectNode: (nodeId: string | null) => {
    set((state) => ({
      selectedNodeId: nodeId,
      nodes: state.nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          isSelected: node.id === nodeId,
        },
      })),
    }));
  },

  getSelectedNode: () => {
    const { nodes, selectedNodeId } = get();
    return nodes.find((n) => n.id === selectedNodeId) || null;
  },

  clearGraph: () => {
    set({
      nodes: [],
      edges: [],
      selectedNodeId: null,
      tabularData: null,
      _rawGraphData: null,
      _collapsedGroups: {},
    });
  },

  updateLayoutConfig: (config: Partial<LayoutConfig>) => {
    set((state) => ({
      layoutConfig: { ...state.layoutConfig, ...config },
    }));
  },

  updateNodeData: (nodeId: string, properties: Record<string, unknown>) => {
    set((state) => ({
      nodes: state.nodes.map((node) => {
        if (node.id !== nodeId) return node;
        const name = typeof properties.name === 'string' ? properties.name : node.data.name;
        return {
          ...node,
          data: { ...node.data, name, properties },
        };
      }),
    }));
  },

  removeNode: (nodeId: string) => {
    set((state) => ({
      nodes: state.nodes.filter((n) => n.id !== nodeId),
      edges: state.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
    }));
  },

  addNode: (node) => {
    set((state) => {
      // Position: rightmost existing node + offset, or (0,0) if empty
      let x = 0;
      let y = 0;
      if (state.nodes.length > 0) {
        const maxX = Math.max(...state.nodes.map((n) => n.position.x));
        const avgY = state.nodes.reduce((sum, n) => sum + n.position.y, 0) / state.nodes.length;
        x = maxX + 200;
        y = avgY;
      }
      const name = String(node.properties.name || node.id);
      const newFlowNode: FlowNode = {
        id: node.id,
        type: 'expanded',
        position: { x, y },
        data: {
          label: node.labels[0] || 'Node',
          name,
          nodeLabel: node.labels[0] || 'Node',
          properties: node.properties,
          role: 'intermediate',
          depth: 1,
          style: { color: '#f59e0b', icon: 'circle', size: 1 },
          isSelected: false,
        },
      };
      return { nodes: [...state.nodes, newFlowNode] };
    });
  },

  addEdge: (edge) => {
    set((state) => {
      const newFlowEdge: FlowEdge = {
        id: edge.id,
        source: edge.source_id,
        target: edge.target_id,
        type: 'animated',
        animated: false,
        data: {
          relationLabel: edge.type,
          properties: {},
        },
      };
      return { edges: [...state.edges, newFlowEdge] };
    });
  },

  expandNode: (nodeId: string) => {
    const { _rawGraphData, _collapsedGroups, nodes: currentNodes } = get();
    if (!_rawGraphData) return;

    const hidden = _collapsedGroups[nodeId];
    if (!hidden || hidden.length === 0) return;

    // 해당 허브의 collapse 해제
    const newCollapsed = { ..._collapsedGroups };
    delete newCollapsed[nodeId];

    // 새 visible 집합 재계산
    const allHidden = new Set(Object.values(newCollapsed).flat());
    const visibleNodes = _rawGraphData.nodes.filter((n) => !allHidden.has(n.id));
    const visibleEdges = _rawGraphData.edges.filter(
      (e) => !allHidden.has(e.source) && !allHidden.has(e.target)
    );

    // 기존 노드 ID 추적 (isNew 마킹용)
    const existingIds = new Set(currentNodes.map((n) => n.id));

    const positions = calculateForceLayout(visibleNodes, visibleEdges);
    const flowNodes = convertToFlowNodes(visibleNodes, positions);
    const flowEdges = convertToFlowEdges(visibleEdges);

    // 새 노드 isNew 마킹 + 남은 허브에 hiddenCount 주입
    for (const node of flowNodes) {
      if (!existingIds.has(node.id)) {
        node.data = { ...node.data, isNew: true };
      }
      const remaining = newCollapsed[node.id];
      if (remaining && remaining.length > 0) {
        node.data = { ...node.data, hiddenCount: remaining.length };
      }
    }

    set({
      nodes: flowNodes,
      edges: flowEdges,
      _collapsedGroups: newCollapsed,
      _layoutVersion: get()._layoutVersion + 1,
    });
  },
}));

export default useGraphStore;
