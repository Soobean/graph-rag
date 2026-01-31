import { useEffect, useCallback, useRef, useMemo } from 'react';
import { Trash2 } from 'lucide-react';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { Button } from '@/components/ui/button';
import { useChatStore, useGraphStore } from '@/stores';
import { useStreamingQuery } from '@/api/hooks';
import type { StreamingMetadata } from '@/types/api';
import { cn } from '@/lib/utils';

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
      onChunk: (chunk: string, fullContent: string) => {
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
          updateMessage(currentAssistantIdRef.current, {
            metadata: {
              intent: metadata.intent,
              intent_confidence: metadata.intent_confidence,
              entities: metadata.entities,
              cypher_query: metadata.cypher_query,
              result_count: metadata.result_count,
              execution_path: metadata.execution_path,
            },
          });
        }
      },
      onComplete: (fullResponse: string, success: boolean) => {
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
    [updateMessage]
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

      // 현재 어시스턴트 메시지 ID 저장
      currentAssistantIdRef.current = assistantId;

      // 스트리밍 API 호출
      startStreaming({
        question: content,
        session_id: currentSessionId || undefined,
      });
    },
    [addMessage, startStreaming, currentSessionId]
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
