import { User, Bot, Loader2, AlertCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';
import type { ChatMessage } from '@/types/chat';

interface MessageItemProps {
  message: ChatMessage;
  className?: string;
}

export function MessageItem({ message, className }: MessageItemProps) {
  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        'flex gap-3 p-4',
        isUser ? 'bg-muted/50' : 'bg-background',
        className
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground'
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Content */}
      <div className="flex-1 space-y-2 overflow-hidden">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">
            {isUser ? 'You' : 'Assistant'}
          </span>
          <span className="text-xs text-muted-foreground">
            {formatTime(message.timestamp)}
          </span>
        </div>

        {/* Message Content */}
        {message.isLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm">Thinking...</span>
          </div>
        ) : message.error ? (
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">{message.error}</span>
          </div>
        ) : (
          <div className="prose prose-sm max-w-none text-foreground prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-pre:my-2 prose-pre:bg-muted prose-pre:text-foreground prose-code:text-foreground prose-code:before:content-none prose-code:after:content-none">
            {isUser ? (
              <p className="whitespace-pre-wrap">{message.content}</p>
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            )}
          </div>
        )}

        {/* Metadata (for assistant messages) */}
        {!isUser && message.metadata && !message.isLoading && (
          <div className="flex flex-wrap gap-2 pt-2">
            <span className="inline-flex items-center rounded-full bg-secondary px-2 py-1 text-xs">
              Intent: {message.metadata.intent}
            </span>
            <span className="inline-flex items-center rounded-full bg-secondary px-2 py-1 text-xs">
              Results: {message.metadata.result_count}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function formatTime(date: Date): string {
  return new Date(date).toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default MessageItem;
