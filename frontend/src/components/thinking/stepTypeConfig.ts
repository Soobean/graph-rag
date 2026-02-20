import type { ElementType } from 'react';
import {
  Search,
  Layers,
  Zap,
  Target,
  MessageSquare,
  Database,
  Clock,
  CheckCircle,
} from 'lucide-react';
import type { StepType } from '@/types/api';

export const stepTypeConfig: Record<StepType, { icon: ElementType; color: string }> = {
  classification: { icon: Search, color: 'text-blue-500' },
  decomposition: { icon: Layers, color: 'text-purple-500' },
  extraction: { icon: Target, color: 'text-orange-500' },
  expansion: { icon: Zap, color: 'text-amber-500' },
  resolution: { icon: CheckCircle, color: 'text-green-500' },
  generation: { icon: MessageSquare, color: 'text-pink-500' },
  execution: { icon: Database, color: 'text-cyan-500' },
  response: { icon: MessageSquare, color: 'text-indigo-500' },
  cache: { icon: Clock, color: 'text-gray-500' },
};
