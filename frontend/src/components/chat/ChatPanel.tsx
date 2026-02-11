import { useEffect, useCallback, useRef, useMemo } from 'react';
import { Trash2 } from 'lucide-react';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { Button } from '@/components/ui/button';
import { useChatStore, useGraphStore, useUiStore } from '@/stores';
import { useStreamingQuery } from '@/api/hooks';
import type { StreamingMetadata, StepType } from '@/types/api';
import { cn } from '@/lib/utils';

// 노드 이름을 스텝 타입으로 변환
function getStepType(nodeName: string): StepType {
  const typeMap: Record<string, StepType> = {
    intent_entity_extractor: 'classification',
    query_decomposer: 'decomposition',
    concept_expander: 'expansion',
    entity_resolver: 'resolution',
    cache_checker: 'cache',
    cypher_generator: 'generation',
    graph_executor: 'execution',
    response_generator: 'response',
    clarification_handler: 'response',
  };
  return typeMap[nodeName] || 'extraction';
}

// 노드 이름을 설명으로 변환
function getStepDescription(nodeName: string, metadata: StreamingMetadata): string {
  const descMap: Record<string, string> = {
    intent_entity_extractor: `의도: ${metadata.intent} (${(metadata.intent_confidence * 100).toFixed(0)}%)`,
    query_decomposer: '쿼리 분해 및 계획 수립',
    concept_expander: `엔티티 확장: ${Object.values(metadata.entities).flat().length}개`,
    entity_resolver: '그래프에서 엔티티 매칭',
    cache_checker: '캐시 확인',
    cypher_generator: 'Cypher 쿼리 생성',
    graph_executor: `쿼리 실행: ${metadata.result_count}건 조회`,
    response_generator: '응답 생성',
    response_generator_empty: '결과 없음 - 기본 응답',
    clarification_handler: '명확화 요청',
  };
  return descMap[nodeName] || nodeName;
}

interface ChatPanelProps {
  className?: string;
}

export function ChatPanel({ className }: ChatPanelProps) {
  const {
    currentSessionId,
    createSession,
    addMessage,
    updateMessage,
    getCurrentMessages,
    clearAllHistory,
  } = useChatStore();

  const { setGraphData, clearGraph } = useGraphStore();
  const { demoRole } = useUiStore();

  const messages = getCurrentMessages();
  const currentAssistantIdRef = useRef<string | null>(null);

  // 세션이 없으면 생성
  useEffect(() => {
    if (!currentSessionId) {
      createSession();
    }
  }, [currentSessionId, createSession]);

  // 스트리밍 콜백을 useMemo로 안정화
  const streamingCallbacks = useMemo(
    () => ({
      onChunk: (_chunk: string, fullContent: string) => {
        // 청크 수신 시 메시지 업데이트 (타이핑 효과)
        if (currentAssistantIdRef.current) {
          updateMessage(currentAssistantIdRef.current, {
            content: fullContent,
          });
        }
      },
      onMetadata: (metadata: StreamingMetadata) => {
        // 메타데이터 수신 시 업데이트
        if (currentAssistantIdRef.current) {
          // execution_path로 기본 thoughtProcess 생성
          const thoughtProcess = {
            steps: (metadata.execution_path ?? []).map((nodeName, idx) => ({
              step_number: idx + 1,
              node_name: nodeName,
              step_type: getStepType(nodeName),
              description: getStepDescription(nodeName, metadata),
              details: {},
            })),
            concept_expansions: Object.entries(metadata.entities ?? {}).map(([entityType, concepts]) => ({
              original_concept: concepts[0] || '',
              entity_type: entityType,
              expansion_strategy: 'normal' as const,
              expanded_concepts: concepts,
              expansion_path: [],
            })),
            execution_path: metadata.execution_path ?? [],
          };

          updateMessage(currentAssistantIdRef.current, {
            metadata: {
              intent: metadata.intent,
              intent_confidence: metadata.intent_confidence,
              entities: metadata.entities,
              cypher_query: metadata.cypher_query,
              result_count: metadata.result_count,
              execution_path: metadata.execution_path,
            },
            thoughtProcess,
          });

          // Graph 데이터가 있으면 graphStore에 설정
          if (metadata.graph_data) {
            setGraphData(metadata.graph_data);
          }
        }
      },
      onComplete: (fullResponse: string) => {
        // 완료 시 최종 업데이트
        if (currentAssistantIdRef.current) {
          updateMessage(currentAssistantIdRef.current, {
            content: fullResponse,
            isLoading: false,
          });
          currentAssistantIdRef.current = null;
        }
      },
      onError: (error: string) => {
        // 에러 발생 시 업데이트
        if (currentAssistantIdRef.current) {
          updateMessage(currentAssistantIdRef.current, {
            isLoading: false,
            error: error || 'An error occurred',
          });
          currentAssistantIdRef.current = null;
        }
      },
    }),
    [updateMessage, setGraphData]
  );

  const { state: streamingState, startStreaming } =
    useStreamingQuery(streamingCallbacks);

  const handleSend = useCallback(
    (content: string) => {
      // 사용자 메시지 추가
      addMessage({
        role: 'user',
        content,
      });

      // 로딩 상태의 어시스턴트 메시지 추가
      const assistantId = addMessage({
        role: 'assistant',
        content: '',
        isLoading: true,
      });

      // 이전 스트리밍이 완료되지 않았으면 로딩 상태 해제 후 ref 초기화
      if (currentAssistantIdRef.current) {
        updateMessage(currentAssistantIdRef.current, { isLoading: false });
        currentAssistantIdRef.current = null;
      }

      // 스트리밍 먼저 시작 (내부 abort()가 이전 스트림을 동기적으로 종료)
      startStreaming(
        { question: content, session_id: currentSessionId || undefined },
        { demoRole }
      );

      // abort 완료 후 새 어시스턴트 ID 설정 (이전 onComplete 발동 불가)
      currentAssistantIdRef.current = assistantId;
    },
    [addMessage, updateMessage, startStreaming, currentSessionId, demoRole]
  );

  const handleClearHistory = useCallback(() => {
    clearAllHistory();
    clearGraph();
    // 새 세션 생성
    createSession();
  }, [clearAllHistory, clearGraph, createSession]);

  return (
    <div className={cn('flex h-full flex-col', className)}>
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-lg font-semibold">Chat</h2>
        <Button
          variant="ghost"
          size="icon"
          onClick={handleClearHistory}
          title="Clear history"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
      <MessageList messages={messages} />
      <ChatInput onSend={handleSend} isLoading={streamingState.isStreaming} />
    </div>
  );
}

export default ChatPanel;
