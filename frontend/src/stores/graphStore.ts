import { create } from 'zustand';
import type { FlowNode, FlowEdge, LayoutConfig } from '../types/graph';
import type { ExplainableGraphData, GraphNode, GraphEdge } from '../types/api';

interface GraphState {
  nodes: FlowNode[];
  edges: FlowEdge[];
  selectedNodeId: string | null;
  layoutConfig: LayoutConfig;

  // Actions
  setGraphData: (data: ExplainableGraphData) => void;
  selectNode: (nodeId: string | null) => void;
  getSelectedNode: () => FlowNode | null;
  clearGraph: () => void;
  updateLayoutConfig: (config: Partial<LayoutConfig>) => void;
  updateNodeData: (nodeId: string, properties: Record<string, unknown>) => void;
  removeNode: (nodeId: string) => void;
  addNode: (node: { id: string; labels: string[]; properties: Record<string, unknown> }) => void;
  addEdge: (edge: { id: string; type: string; source_id: string; target_id: string }) => void;
}

/**
 * 엣지 방향을 분석하여 자연스러운 시작 노드 찾기
 * (들어오는 엣지가 없거나 적은 노드 = 시작점)
 */
function findNaturalStartNodes(
  nodes: GraphNode[],
  edges: GraphEdge[]
): string[] {
  const nodeIds = new Set(nodes.map(n => n.id));
  const inDegree = new Map<string, number>();
  const outDegree = new Map<string, number>();

  // 초기화
  nodes.forEach(n => {
    inDegree.set(n.id, 0);
    outDegree.set(n.id, 0);
  });

  // 차수 계산
  edges.forEach(edge => {
    if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
      outDegree.set(edge.source, (outDegree.get(edge.source) || 0) + 1);
      inDegree.set(edge.target, (inDegree.get(edge.target) || 0) + 1);
    }
  });

  // 들어오는 엣지가 0인 노드들 = 자연스러운 시작점
  const zeroInDegree = nodes.filter(n => inDegree.get(n.id) === 0).map(n => n.id);
  if (zeroInDegree.length > 0) {
    return zeroInDegree;
  }

  // 없으면 inDegree가 가장 낮은 노드들 선택
  const minInDegree = Math.min(...Array.from(inDegree.values()));
  return nodes.filter(n => inDegree.get(n.id) === minInDegree).map(n => n.id);
}

/**
 * BFS로 시작 노드들로부터의 hop 거리 계산 (방향성 고려)
 */
function calculateHopDistances(
  nodes: GraphNode[],
  edges: GraphEdge[],
  startNodeIds: string[]
): Map<string, number> {
  const distances = new Map<string, number>();
  const nodeIds = new Set(nodes.map(n => n.id));

  // 방향성 인접 리스트 (source → target 방향으로만)
  const forwardAdjacency = new Map<string, string[]>();
  // 양방향 인접 리스트 (fallback용)
  const bidirectionalAdjacency = new Map<string, string[]>();

  nodes.forEach(n => {
    forwardAdjacency.set(n.id, []);
    bidirectionalAdjacency.set(n.id, []);
  });

  edges.forEach(edge => {
    if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
      forwardAdjacency.get(edge.source)?.push(edge.target);
      bidirectionalAdjacency.get(edge.source)?.push(edge.target);
      bidirectionalAdjacency.get(edge.target)?.push(edge.source);
    }
  });

  // BFS (먼저 방향성 탐색 시도)
  const queue: { id: string; distance: number }[] = [];

  // 시작 노드들 초기화
  startNodeIds.forEach(id => {
    if (nodeIds.has(id)) {
      distances.set(id, 0);
      queue.push({ id, distance: 0 });
    }
  });

  // 시작 노드가 없으면 모든 노드를 거리 0으로 설정
  if (queue.length === 0) {
    nodes.forEach(n => distances.set(n.id, 0));
    return distances;
  }

  // 방향성 BFS
  while (queue.length > 0) {
    const { id, distance } = queue.shift()!;
    const neighbors = forwardAdjacency.get(id) || [];

    for (const neighborId of neighbors) {
      if (!distances.has(neighborId)) {
        distances.set(neighborId, distance + 1);
        queue.push({ id: neighborId, distance: distance + 1 });
      }
    }
  }

  // 아직 방문하지 않은 노드는 양방향으로 탐색
  const unvisited = nodes.filter(n => !distances.has(n.id));
  if (unvisited.length > 0) {
    // 이미 방문한 노드들에서 시작하여 양방향 탐색
    const visited = nodes.filter(n => distances.has(n.id));
    for (const node of visited) {
      queue.push({ id: node.id, distance: distances.get(node.id)! });
    }

    while (queue.length > 0) {
      const { id, distance } = queue.shift()!;
      const neighbors = bidirectionalAdjacency.get(id) || [];

      for (const neighborId of neighbors) {
        if (!distances.has(neighborId)) {
          distances.set(neighborId, distance + 1);
          queue.push({ id: neighborId, distance: distance + 1 });
        }
      }
    }
  }

  // 연결되지 않은 노드는 최대 거리 + 1로 설정
  const maxDistance = Math.max(...Array.from(distances.values()), 0);
  nodes.forEach(n => {
    if (!distances.has(n.id)) {
      distances.set(n.id, maxDistance + 1);
    }
  });

  return distances;
}

/**
 * Hop 거리 기반 레이아웃 계산
 * 백엔드의 depth 정보를 우선 사용하고, 엣지 연결 정보로 보완
 */
function calculateLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  startNodeIds: string[],
  config: LayoutConfig
): Map<string, { x: number; y: number; depth: number }> {
  const positions = new Map<string, { x: number; y: number; depth: number }>();

  // 1. 먼저 백엔드에서 제공한 depth 정보 사용
  const backendDepths = new Map<string, number>();
  nodes.forEach(node => {
    if (node.depth !== undefined && node.depth >= 0) {
      backendDepths.set(node.id, node.depth);
    }
  });

  // 2. 엣지가 있으면 BFS로 보완, 없으면 백엔드 depth만 사용
  let finalDepths: Map<string, number>;

  if (edges.length > 0) {
    // BFS로 hop 거리 계산
    const hopDistances = calculateHopDistances(nodes, edges, startNodeIds);

    // BFS 결과가 있는 노드는 BFS 사용, 없으면 백엔드 depth 사용
    finalDepths = new Map<string, number>();
    nodes.forEach(node => {
      const bfsDepth = hopDistances.get(node.id);
      const backendDepth = backendDepths.get(node.id) ?? 2;

      // BFS가 성공적으로 거리를 계산했으면 사용, 아니면 백엔드 depth 사용
      if (bfsDepth !== undefined && bfsDepth < nodes.length) {
        finalDepths.set(node.id, bfsDepth);
      } else {
        finalDepths.set(node.id, backendDepth);
      }
    });
  } else {
    // 엣지가 없으면 백엔드 depth만 사용
    finalDepths = backendDepths;
    nodes.forEach(node => {
      if (!finalDepths.has(node.id)) {
        // role 기반 기본 depth
        const defaultDepth = node.role === 'start' ? 0 : node.role === 'intermediate' ? 1 : 2;
        finalDepths.set(node.id, defaultDepth);
      }
    });
  }

  // depth별로 노드 그룹화
  const nodesByDepth = new Map<number, GraphNode[]>();
  nodes.forEach((node) => {
    const depth = finalDepths.get(node.id) ?? 2;
    if (!nodesByDepth.has(depth)) {
      nodesByDepth.set(depth, []);
    }
    nodesByDepth.get(depth)!.push(node);
  });

  // 각 depth의 노드들에 좌표 할당
  nodesByDepth.forEach((depthNodes, depth) => {
    const totalNodes = depthNodes.length;
    const startY = -((totalNodes - 1) * config.nodeSpacingY) / 2;

    depthNodes.forEach((node, index) => {
      const x = depth * config.depthSpacing;
      const y = startY + index * config.nodeSpacingY;

      if (config.direction === 'TB') {
        // Top to Bottom: x와 y 스왑
        positions.set(node.id, { x: y, y: x, depth });
      } else {
        // Left to Right
        positions.set(node.id, { x, y, depth });
      }
    });
  });

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

  setGraphData: (data: ExplainableGraphData) => {
    const { layoutConfig } = get();

    // 시작 노드 결정: 백엔드의 query_entity_ids 우선, 없으면 엣지 방향 분석
    let startNodeIds = data.query_entity_ids || [];
    if (startNodeIds.length === 0) {
      // 백엔드에서 시작점을 제공하지 않으면 엣지 방향 분석으로 찾기
      startNodeIds = findNaturalStartNodes(data.nodes, data.edges);
    }

    const positions = calculateLayout(data.nodes, data.edges, startNodeIds, layoutConfig);
    const flowNodes = convertToFlowNodes(data.nodes, positions);
    const flowEdges = convertToFlowEdges(data.edges);

    set({
      nodes: flowNodes,
      edges: flowEdges,
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
}));

export default useGraphStore;
