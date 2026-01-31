import { useState, useCallback, useRef } from 'react';
import type {
  QueryRequest,
  StreamingMetadata,
  StreamingEvent,
} from '../../types/api';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export interface StreamingQueryState {
  isStreaming: boolean;
  content: string;
  metadata: StreamingMetadata | null;
  error: string | null;
  isComplete: boolean;
}

export interface StreamingQueryCallbacks {
  onChunk?: (chunk: string, fullContent: string) => void;
  onMetadata?: (metadata: StreamingMetadata) => void;
  onComplete?: (fullResponse: string, success: boolean) => void;
  onError?: (error: string) => void;
}

export interface UseStreamingQueryReturn {
  state: StreamingQueryState;
  startStreaming: (request: QueryRequest) => Promise<void>;
  abort: () => void;
}

export function useStreamingQuery(
  callbacks?: StreamingQueryCallbacks
): UseStreamingQueryReturn {
  const [state, setState] = useState<StreamingQueryState>({
    isStreaming: false,
    content: '',
    metadata: null,
    error: null,
    isComplete: false,
  });

  const abortControllerRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setState((prev) => ({
      ...prev,
      isStreaming: false,
    }));
  }, []);

  const startStreaming = useCallback(
    async (request: QueryRequest) => {
      // Abort any existing stream
      abort();

      // Create new abort controller
      abortControllerRef.current = new AbortController();

      // Reset state
      setState({
        isStreaming: true,
        content: '',
        metadata: null,
        error: null,
        isComplete: false,
      });

      let accumulatedContent = '';

      try {
        const response = await fetch(`${API_BASE_URL}/query/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
          },
          body: JSON.stringify({
            question: request.question,
            session_id: request.session_id,
          }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('Response body is not readable');
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            break;
          }

          buffer += decoder.decode(value, { stream: true });

          // Parse SSE events from buffer
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          let currentEvent: { event?: string; data?: string } = {};

          for (const line of lines) {
            if (line.startsWith('event:')) {
              currentEvent.event = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              currentEvent.data = line.slice(5).trim();
            } else if (line === '' && currentEvent.event && currentEvent.data) {
              // Process complete event
              const eventType = currentEvent.event;
              const eventData = currentEvent.data;

              if (eventType === 'metadata') {
                try {
                  const metadata = JSON.parse(eventData) as StreamingMetadata;
                  setState((prev) => ({ ...prev, metadata }));
                  callbacks?.onMetadata?.(metadata);
                } catch {
                  console.error('Failed to parse metadata:', eventData);
                }
              } else if (eventType === 'chunk') {
                accumulatedContent += eventData;
                setState((prev) => ({
                  ...prev,
                  content: accumulatedContent,
                }));
                callbacks?.onChunk?.(eventData, accumulatedContent);
              } else if (eventType === 'done') {
                try {
                  const doneData = JSON.parse(eventData) as {
                    success: boolean;
                    full_response: string;
                  };
                  setState((prev) => ({
                    ...prev,
                    isStreaming: false,
                    isComplete: true,
                    content: doneData.full_response || accumulatedContent,
                  }));
                  callbacks?.onComplete?.(
                    doneData.full_response || accumulatedContent,
                    doneData.success
                  );
                } catch {
                  setState((prev) => ({
                    ...prev,
                    isStreaming: false,
                    isComplete: true,
                  }));
                  callbacks?.onComplete?.(accumulatedContent, true);
                }
              } else if (eventType === 'error') {
                try {
                  const errorData = JSON.parse(eventData) as { message: string };
                  setState((prev) => ({
                    ...prev,
                    isStreaming: false,
                    error: errorData.message,
                  }));
                  callbacks?.onError?.(errorData.message);
                } catch {
                  setState((prev) => ({
                    ...prev,
                    isStreaming: false,
                    error: eventData,
                  }));
                  callbacks?.onError?.(eventData);
                }
              }

              // Reset for next event
              currentEvent = {};
            }
          }
        }
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          // Intentional abort, not an error
          return;
        }

        const errorMessage =
          error instanceof Error ? error.message : 'Unknown error occurred';
        setState((prev) => ({
          ...prev,
          isStreaming: false,
          error: errorMessage,
        }));
        callbacks?.onError?.(errorMessage);
      } finally {
        abortControllerRef.current = null;
      }
    },
    [abort, callbacks]
  );

  return {
    state,
    startStreaming,
    abort,
  };
}

export default useStreamingQuery;
