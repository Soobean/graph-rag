import type { QueryMetadata, ExplainableGraphData, ThoughtProcessVisualization } from './api';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  metadata?: QueryMetadata;
  graphData?: ExplainableGraphData;
  thoughtProcess?: ThoughtProcessVisualization;
  isLoading?: boolean;
  error?: string;
}

export interface ChatSession {
  id: string;
  messages: ChatMessage[];
  createdAt: Date;
}
