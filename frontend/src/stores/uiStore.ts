import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type DemoRole = 'admin' | 'manager' | 'editor' | 'viewer';

interface UiState {
  // 패널 크기 (퍼센트)
  leftPanelWidth: number;
  rightPanelWidth: number;

  // 패널 가시성
  isThinkingPanelOpen: boolean;
  isNodeDetailOpen: boolean;

  // 현재 활성 탭
  activeRightTab: 'graph' | 'thinking';

  // 데모 역할
  demoRole: DemoRole;

  // Actions
  setLeftPanelWidth: (width: number) => void;
  setRightPanelWidth: (width: number) => void;
  toggleThinkingPanel: () => void;
  toggleNodeDetail: () => void;
  setActiveRightTab: (tab: 'graph' | 'thinking') => void;
  setDemoRole: (role: DemoRole) => void;
  resetLayout: () => void;
}

const DEFAULT_LEFT_WIDTH = 35;
const DEFAULT_RIGHT_WIDTH = 65;

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      leftPanelWidth: DEFAULT_LEFT_WIDTH,
      rightPanelWidth: DEFAULT_RIGHT_WIDTH,
      isThinkingPanelOpen: false,
      isNodeDetailOpen: false,
      activeRightTab: 'graph',
      demoRole: 'admin',

      setLeftPanelWidth: (width: number) => {
        const clampedWidth = Math.min(Math.max(width, 20), 60);
        set({
          leftPanelWidth: clampedWidth,
          rightPanelWidth: 100 - clampedWidth,
        });
      },

      setRightPanelWidth: (width: number) => {
        const clampedWidth = Math.min(Math.max(width, 40), 80);
        set({
          rightPanelWidth: clampedWidth,
          leftPanelWidth: 100 - clampedWidth,
        });
      },

      toggleThinkingPanel: () => {
        set((state) => ({
          isThinkingPanelOpen: !state.isThinkingPanelOpen,
        }));
      },

      toggleNodeDetail: () => {
        set((state) => ({
          isNodeDetailOpen: !state.isNodeDetailOpen,
        }));
      },

      setActiveRightTab: (tab: 'graph' | 'thinking') => {
        set({ activeRightTab: tab });
      },

      setDemoRole: (role: DemoRole) => {
        set({ demoRole: role });
      },

      resetLayout: () => {
        set({
          leftPanelWidth: DEFAULT_LEFT_WIDTH,
          rightPanelWidth: DEFAULT_RIGHT_WIDTH,
        });
      },
    }),
    {
      name: 'graph-rag-ui',
      partialize: (state) => ({
        leftPanelWidth: state.leftPanelWidth,
        rightPanelWidth: state.rightPanelWidth,
        demoRole: state.demoRole,
      }),
    }
  )
);

export default useUiStore;
