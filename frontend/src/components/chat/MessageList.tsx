import { useEffect, useRef } from 'react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { MessageItem } from './MessageItem';
import type { ChatMessage } from '@/types/chat';
import { cn } from '@/lib/utils';

interface MessageListProps {
  messages: ChatMessage[];
  className?: string;
}

export function MessageList({ messages, className }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // 새 메시지가 추가되면 스크롤
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className={cn('flex flex-1 items-center justify-center p-8', className)}>
        <div className="text-center text-muted-foreground">
          <p className="text-lg font-medium">Graph RAG Chat</p>
          <p className="text-sm mt-2">질문을 입력하여 그래프 데이터를 검색하세요.</p>
        </div>
      </div>
    );
  }

  return (
    <ScrollArea className={cn('flex-1', className)}>
      <div>
        {messages.map((message) => (
          <MessageItem key={message.id} message={message} />
        ))}
      </div>
      <div ref={bottomRef} />
    </ScrollArea>
  );
}

export default MessageList;
