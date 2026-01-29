import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ChatMessage, ChatSession } from '../types/chat';

interface ChatState {
  sessions: ChatSession[];
  currentSessionId: string | null;

  // Actions
  createSession: () => string;
  setCurrentSession: (sessionId: string) => void;
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => string;
  updateMessage: (messageId: string, updates: Partial<ChatMessage>) => void;
  getCurrentSession: () => ChatSession | null;
  getCurrentMessages: () => ChatMessage[];
  clearCurrentSession: () => void;
  clearAllHistory: () => void;
}

// crypto.randomUUID()는 HTTPS에서만 동작하므로 폴백 추가
const generateId = (): string => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // HTTP 환경용 폴백
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      sessions: [],
      currentSessionId: null,

      createSession: () => {
        const newSession: ChatSession = {
          id: generateId(),
          messages: [],
          createdAt: new Date(),
        };
        set((state) => ({
          sessions: [...state.sessions, newSession],
          currentSessionId: newSession.id,
        }));
        return newSession.id;
      },

      setCurrentSession: (sessionId: string) => {
        set({ currentSessionId: sessionId });
      },

      addMessage: (message) => {
        const messageId = generateId();
        const newMessage: ChatMessage = {
          ...message,
          id: messageId,
          timestamp: new Date(),
        };

        set((state) => {
          const { currentSessionId, sessions } = state;
          if (!currentSessionId) return state;

          return {
            sessions: sessions.map((session) =>
              session.id === currentSessionId
                ? { ...session, messages: [...session.messages, newMessage] }
                : session
            ),
          };
        });

        return messageId;
      },

      updateMessage: (messageId: string, updates: Partial<ChatMessage>) => {
        set((state) => ({
          sessions: state.sessions.map((session) => ({
            ...session,
            messages: session.messages.map((msg) =>
              msg.id === messageId ? { ...msg, ...updates } : msg
            ),
          })),
        }));
      },

      getCurrentSession: () => {
        const { sessions, currentSessionId } = get();
        return sessions.find((s) => s.id === currentSessionId) || null;
      },

      getCurrentMessages: () => {
        const session = get().getCurrentSession();
        return session?.messages || [];
      },

      clearCurrentSession: () => {
        set((state) => {
          const { currentSessionId, sessions } = state;
          if (!currentSessionId) return state;

          return {
            sessions: sessions.map((session) =>
              session.id === currentSessionId
                ? { ...session, messages: [] }
                : session
            ),
          };
        });
      },

      clearAllHistory: () => {
        set({
          sessions: [],
          currentSessionId: null,
        });
      },
    }),
    {
      name: 'graph-rag-chat',
      partialize: (state) => ({
        sessions: state.sessions,
        currentSessionId: state.currentSessionId,
      }),
    }
  )
);

export default useChatStore;
