import { useEffect, useCallback, useMemo, useRef } from 'react';
import { Trash2, PanelRightOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { Button } from '@/components/ui/button';
import { useChatStore, useGraphStore, useUiStore } from '@/stores';
import { useStreamingQuery } from '@/api/hooks';
import type { StreamingMetadata, StreamingStepData, StepType, ThoughtStep } from '@/types/api';
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
    setStreamingMessageId,
    getCurrentMessages,
    clearAllHistory,
  } = useChatStore();

  const { setGraphData, setTabularData, clearGraph } = useGraphStore();
  const { demoRole, isRightPanelOpen, openRightPanel, closeRightPanel } = useUiStore();

  const messages = getCurrentMessages();

  // 세션이 없으면 생성
  useEffect(() => {
    if (!currentSessionId) {
      createSession();
    }
  }, [currentSessionId, createSession]);

  // 실시간 step 누적용 ref (콜백 간 공유, 리렌더 없이 최신 값 유지)
  const stepsRef = useRef<ThoughtStep[]>([]);

  // 스트리밍 콜백을 useMemo로 안정화
  // useChatStore.getState()로 최신 streamingMessageId를 읽어 dependency 없이 항상 최신 값 사용
  const streamingCallbacks = useMemo(
    () => ({
      onChunk: (_chunk: string, fullContent: string) => {
        const streamingId = useChatStore.getState().currentStreamingMessageId;
        if (streamingId) {
          updateMessage(streamingId, {
            content: fullContent,
          });
        }
      },
      onStep: (stepData: StreamingStepData) => {
        const streamingId = useChatStore.getState().currentStreamingMessageId;
        if (!streamingId) return;

        const newStep: ThoughtStep = {
          step_number: stepData.step_number,
          node_name: stepData.node_name,
          step_type: getStepType(stepData.node_name),
          description: stepData.description,
          details: {},
        };

        stepsRef.current = [...stepsRef.current, newStep];

        updateMessage(streamingId, {
          thoughtProcess: {
            steps: [...stepsRef.current],
            concept_expansions: [],
            execution_path: stepsRef.current.map((s) => s.node_name),
          },
        });
      },
      onMetadata: (metadata: StreamingMetadata) => {
        const streamingId = useChatStore.getState().currentStreamingMessageId;
        if (!streamingId) return;

        // step 이벤트로 이미 steps가 채워진 경우 → thoughtProcess를 덮어쓰지 않음
        // step 이벤트가 없었던 경우(구버전 호환) → metadata.execution_path로 빌드
        const updates: Partial<import('@/types/chat').ChatMessage> = {
          metadata: {
            intent: metadata.intent,
            intent_confidence: metadata.intent_confidence,
            entities: metadata.entities,
            cypher_query: metadata.cypher_query,
            result_count: metadata.result_count,
            execution_path: metadata.execution_path,
          },
        };

        if (stepsRef.current.length === 0 && metadata.execution_path?.length) {
          updates.thoughtProcess = {
            steps: metadata.execution_path.map((nodeName, idx) => ({
              step_number: idx + 1,
              node_name: nodeName,
              step_type: getStepType(nodeName),
              description: getStepDescription(nodeName, metadata),
              details: {},
            })),
            concept_expansions: Object.entries(metadata.entities ?? {}).map(
              ([entityType, concepts]) => ({
                original_concept: concepts[0] || '',
                entity_type: entityType,
                expansion_strategy: 'normal' as const,
                expanded_concepts: concepts,
                expansion_path: [],
              })
            ),
            execution_path: metadata.execution_path,
          };
        }

        updateMessage(streamingId, updates);

        if (metadata.graph_data) {
          setGraphData(metadata.graph_data);
          openRightPanel();
        } else if (metadata.tabular_data) {
          setTabularData(metadata.tabular_data);
          openRightPanel();
        }
      },
      onComplete: (fullResponse: string) => {
        const streamingId = useChatStore.getState().currentStreamingMessageId;
        if (streamingId) {
          updateMessage(streamingId, {
            content: fullResponse,
            isLoading: false,
          });
          setStreamingMessageId(null);
        }
      },
      onError: (error: string) => {
        const streamingId = useChatStore.getState().currentStreamingMessageId;
        if (streamingId) {
          updateMessage(streamingId, {
            isLoading: false,
            error: error || 'An error occurred',
          });
          setStreamingMessageId(null);
        }
      },
    }),
    [updateMessage, setStreamingMessageId, setGraphData, setTabularData, openRightPanel]
  );

  const { state: streamingState, startStreaming } =
    useStreamingQuery(streamingCallbacks);

  const handleSend = useCallback(
    (content: string) => {
      // 새 쿼리 시작 → step 누적 초기화
      stepsRef.current = [];

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

      // 이전 스트리밍이 완료되지 않았으면 로딩 상태 해제
      const prevStreamingId = useChatStore.getState().currentStreamingMessageId;
      if (prevStreamingId) {
        updateMessage(prevStreamingId, { isLoading: false });
      }

      // 새 어시스턴트 ID를 먼저 설정 (콜백이 최신 ID를 읽을 수 있도록)
      setStreamingMessageId(assistantId);

      // 스트리밍 시작 (내부 abort()가 이전 스트림을 동기적으로 종료)
      startStreaming(
        { question: content, session_id: currentSessionId || undefined },
        { demoRole }
      );
    },
    [addMessage, updateMessage, setStreamingMessageId, startStreaming, currentSessionId, demoRole]
  );

  const handleClearHistory = useCallback(() => {
    clearAllHistory();
    clearGraph();
    closeRightPanel();
    createSession();
  }, [clearAllHistory, clearGraph, closeRightPanel, createSession]);

  const isLanding = messages.length === 0;

  return (
    <div className={cn('flex h-full flex-col', className)}>
      <AnimatePresence mode="wait">
        {isLanding ? (
          // ── 랜딩 모드 ──
          <motion.div
            key="landing"
            className="flex flex-1 flex-col items-center justify-center"
            exit={{ opacity: 0, y: -30, transition: { duration: 0.2 } }}
          >
            <h2 className="mb-2 text-center text-2xl font-semibold text-foreground/80">
              Graph RAG Explorer
            </h2>
            <p className="mb-8 text-center text-sm text-muted-foreground">
              질문을 입력하여 그래프 데이터를 검색하세요.
            </p>
            {/* layoutId로 입력창 공유 애니메이션 */}
            <motion.div layoutId="chat-input" className="w-full max-w-2xl px-4">
              <ChatInput onSend={handleSend} isLoading={streamingState.isStreaming} className="border-t-0" />
            </motion.div>
          </motion.div>
        ) : (
          // ── 대화 모드 ──
          <motion.div
            key="conversation"
            className="flex flex-1 flex-col min-h-0"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4, delay: 0.1 }}
          >
            {/* 헤더 슬라이드 다운 */}
            <motion.div
              className="flex items-center justify-between border-b border-border px-4 py-3"
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.15 }}
            >
              <h2 className="text-lg font-semibold">Chat</h2>
              <div className="flex items-center gap-1">
                {!isRightPanelOpen && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={openRightPanel}
                    title="그래프 패널 열기"
                  >
                    <PanelRightOpen className="h-4 w-4" />
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleClearHistory}
                  title="Clear history"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </motion.div>

            {/* 메시지 리스트 페이드인 */}
            <motion.div
              className="flex-1 min-h-0"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.25 }}
            >
              <MessageList messages={messages} />
            </motion.div>

            {/* layoutId로 입력창 공유 애니메이션 (중앙 → 하단) */}
            <motion.div layoutId="chat-input" className="w-full">
              <ChatInput onSend={handleSend} isLoading={streamingState.isStreaming} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default ChatPanel;
