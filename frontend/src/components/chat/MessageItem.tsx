import { useState } from 'react';
import { Loader2, AlertCircle, ChevronRight, CheckCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';
import { stepTypeConfig } from '@/components/thinking/stepTypeConfig';
import type { ChatMessage } from '@/types/chat';
import type { ThoughtProcessVisualization } from '@/types/api';

interface MessageItemProps {
  message: ChatMessage;
  className?: string;
}

/** 미니멀 유저 실루엣 아이콘 */
function UserAvatar() {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-200">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        className="h-4 w-4 text-gray-500"
      >
        <circle cx="12" cy="8" r="4" fill="currentColor" />
        <path
          d="M4 20c0-3.3 3.6-6 8-6s8 2.7 8 6"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

/** AI 브랜드 아이콘 — 그라데이션 원형 + 그래프 심볼 */
function AIAvatar() {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-violet-500">
      <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5 text-white">
        <circle cx="12" cy="7" r="2" fill="currentColor" />
        <circle cx="6" cy="17" r="2" fill="currentColor" />
        <circle cx="18" cy="17" r="2" fill="currentColor" />
        <path
          d="M12 9v3M8.5 15.5 11 12.5M15.5 15.5 13 12.5"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

/** 인라인 파이프라인 단계 표시 — 로딩 중 스텝 순차 등장, 완료 후 접기 전환 */
function InlineThinking({ thoughtProcess, isLoading }: {
  thoughtProcess: ThoughtProcessVisualization;
  isLoading: boolean;
}) {
  const [manualToggle, setManualToggle] = useState<boolean | null>(null);
  const [prevIsLoading, setPrevIsLoading] = useState(isLoading);

  if (prevIsLoading !== isLoading) {
    setPrevIsLoading(isLoading);
    setManualToggle(null);
  }

  const isOpen = manualToggle ?? isLoading;
  const steps = thoughtProcess.steps;
  if (steps.length === 0) return null;

  // 완료 후 접힌 상태 → 토글 헤더만 표시
  if (!isLoading && !isOpen) {
    return (
      <div className="mb-2">
        <button
          type="button"
          onClick={() => setManualToggle(true)}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted/50 transition-colors"
        >
          <ChevronRight className="h-3.5 w-3.5" />
          <CheckCircle className="h-3 w-3 text-green-500" />
          <span>파이프라인 {steps.length}단계 완료</span>
        </button>
      </div>
    );
  }

  return (
    <div className="mb-2">
      {/* 펼침 상태 헤더 (완료 후 수동 펼침 시) */}
      {!isLoading && (
        <button
          type="button"
          onClick={() => setManualToggle(false)}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 mb-1.5 text-xs text-muted-foreground hover:bg-muted/50 transition-colors"
        >
          <ChevronRight className="h-3.5 w-3.5 rotate-90 transition-transform duration-200" />
          <CheckCircle className="h-3 w-3 text-green-500" />
          <span>파이프라인 {steps.length}단계 완료</span>
        </button>
      )}

      {/* 스텝 목록 — 순차 등장 애니메이션 */}
      <div className="ml-2 border-l-2 border-border pl-3 space-y-1">
        {steps.map((step, idx) => {
          const config = stepTypeConfig[step.step_type] || { icon: CheckCircle, color: 'text-gray-500' };
          const Icon = config.icon;
          const isLastStep = idx === steps.length - 1;
          const isRunning = isLoading && isLastStep;

          return (
            <div
              key={step.step_number}
              className="flex items-center gap-2 text-xs animate-in fade-in-0 slide-in-from-left-2"
              style={{ animationDuration: '200ms' }}
            >
              <Icon className={cn('h-3.5 w-3.5 shrink-0', config.color)} />
              <span className="text-muted-foreground">{step.description}</span>
              {isRunning && (
                <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** 로딩 초기 상태 — 메타데이터 도착 전 3-dot 펄스 */
function LoadingDots() {
  return (
    <div className="mb-2 ml-2 border-l-2 border-border pl-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
        <span>파이프라인 시작 중</span>
      </div>
    </div>
  );
}

export function MessageItem({ message, className }: MessageItemProps) {
  const isUser = message.role === 'user';
  const thoughtProcess = !isUser ? message.thoughtProcess : undefined;
  const hasThoughtProcess = !!thoughtProcess && thoughtProcess.steps.length > 0;

  return (
    <div
      className={cn(
        'px-4 py-5',
        isUser ? 'bg-transparent' : 'bg-gray-50/80',
        className
      )}
    >
      <div className="mx-auto flex max-w-3xl gap-3">
        {/* Avatar */}
        {isUser ? <UserAvatar /> : <AIAvatar />}

        {/* Content */}
        <div className="flex-1 space-y-1.5 overflow-hidden pt-0.5">
          {/* 발화자 + 시간 */}
          <div className="flex items-center gap-1.5">
            <span className={cn(
              'text-xs font-medium',
              isUser ? 'text-gray-500' : 'text-blue-600/80'
            )}>
              {isUser ? '나' : 'Graph RAG'}
            </span>
            <span className="text-[10px] text-gray-300">
              {formatTime(message.timestamp)}
            </span>
          </div>

          {/* 파이프라인 스텝 (로딩 중 순차 표시 / 완료 후 접기) */}
          {message.isLoading && !hasThoughtProcess && !isUser && (
            <LoadingDots />
          )}
          {hasThoughtProcess && thoughtProcess && (
            <InlineThinking
              thoughtProcess={thoughtProcess}
              isLoading={!!message.isLoading}
            />
          )}

          {/* Message Content */}
          {message.error ? (
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-4 w-4" />
              <span className="text-sm">{message.error}</span>
            </div>
          ) : message.content ? (
            <div className="prose prose-sm max-w-none text-foreground leading-relaxed prose-p:my-1.5 prose-p:leading-relaxed prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:leading-relaxed prose-pre:my-2 prose-pre:bg-muted prose-pre:text-foreground prose-code:text-foreground prose-code:before:content-none prose-code:after:content-none">
              {isUser ? (
                <p className="whitespace-pre-wrap">{message.content}</p>
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              )}
            </div>
          ) : null}

          {/* Metadata (for assistant messages) */}
          {!isUser && message.metadata && !message.isLoading && (
            <div className="flex flex-wrap gap-2 pt-2">
              <span className="inline-flex items-center rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-600">
                {message.metadata.intent}
              </span>
              <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-600">
                {message.metadata.result_count} results
              </span>
            </div>
          )}
        </div>
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
