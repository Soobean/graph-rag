import { useEffect, useCallback } from 'react';
import { Trash2 } from 'lucide-react';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { Button } from '@/components/ui/button';
import { useChatStore, useGraphStore } from '@/stores';
import { useQueryApi } from '@/api/hooks';
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

  // 세션이 없으면 생성
  useEffect(() => {
    if (!currentSessionId) {
      createSession();
    }
  }, [currentSessionId, createSession]);

  const queryMutation = useQueryApi({
    onSuccess: (data) => {
      // 응답 메시지 업데이트
      const assistantMessageId = messages.find(
        (m) => m.role === 'assistant' && m.isLoading
      )?.id;

      if (assistantMessageId) {
        updateMessage(assistantMessageId, {
          content: data.response,
          metadata: data.metadata,
          graphData: data.explanation?.graph_data || undefined,
          thoughtProcess: data.explanation?.thought_process || undefined,
          isLoading: false,
        });

        // 그래프 데이터 업데이트
        if (data.explanation?.graph_data) {
          setGraphData(data.explanation.graph_data);
        }
      }
    },
    onError: (error) => {
      const assistantMessageId = messages.find(
        (m) => m.role === 'assistant' && m.isLoading
      )?.id;

      if (assistantMessageId) {
        updateMessage(assistantMessageId, {
          isLoading: false,
          error: error.message || 'An error occurred',
        });
      }
    },
  });

  const handleSend = useCallback(
    (content: string) => {
      // 사용자 메시지 추가
      addMessage({
        role: 'user',
        content,
      });

      // 로딩 상태의 어시스턴트 메시지 추가
      addMessage({
        role: 'assistant',
        content: '',
        isLoading: true,
      });

      // API 호출
      queryMutation.mutate({
        question: content,
        session_id: currentSessionId || undefined,
        include_explanation: true,
        include_graph: true,
      });
    },
    [addMessage, queryMutation, currentSessionId]
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
      <ChatInput onSend={handleSend} isLoading={queryMutation.isPending} />
    </div>
  );
}

export default ChatPanel;
