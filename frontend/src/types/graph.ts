import type { Node, Edge } from '@xyflow/react';
import type { NodeStyle } from './api';

// React Flow 노드 데이터 타입
export interface FlowNodeData extends Record<string, unknown> {
  label: string;
  name: string;
  nodeLabel: string;  // Employee, Skill 등
  properties: Record<string, unknown>;
  role: 'start' | 'intermediate' | 'end';
  depth: number;
  style: NodeStyle;
  isSelected?: boolean;
}

// React Flow 노드 타입
export type FlowNode = Node<FlowNodeData, 'query' | 'expanded' | 'result'>;

// React Flow 엣지 데이터 타입
export interface FlowEdgeData extends Record<string, unknown> {
  relationLabel: string;
  properties: Record<string, unknown>;
}

// React Flow 엣지 타입
export type FlowEdge = Edge<FlowEdgeData>;

// 레이아웃 설정
export interface LayoutConfig {
  direction: 'LR' | 'TB';
  nodeSpacingY: number;
  depthSpacing: number;
}

export const DEFAULT_LAYOUT_CONFIG: LayoutConfig = {
  direction: 'LR',
  nodeSpacingY: 80,
  depthSpacing: 280,
};
