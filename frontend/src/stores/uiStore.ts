import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type DemoRole = 'admin' | 'manager' | 'editor' | 'viewer';

interface UiState {
  // 패널 크기 (퍼센트) — right는 100 - left로 파생
  leftPanelWidth: number;

  // 패널 가시성
  isRightPanelOpen: boolean;

  // 데모 역할
  demoRole: DemoRole;

  // Actions
  setLeftPanelWidth: (width: number) => void;
  openRightPanel: () => void;
  closeRightPanel: () => void;
  setDemoRole: (role: DemoRole) => void;
}

const DEFAULT_LEFT_WIDTH = 35;

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      leftPanelWidth: DEFAULT_LEFT_WIDTH,
      isRightPanelOpen: false,
      demoRole: 'admin',

      setLeftPanelWidth: (width: number) => {
        const clampedWidth = Math.min(Math.max(width, 20), 60);
        set({ leftPanelWidth: clampedWidth });
      },

      openRightPanel: () => set({ isRightPanelOpen: true }),
      closeRightPanel: () => set({ isRightPanelOpen: false }),

      setDemoRole: (role: DemoRole) => {
        set({ demoRole: role });
      },
    }),
    {
      name: 'graph-rag-ui',
      partialize: (state) => ({
        leftPanelWidth: state.leftPanelWidth,
        demoRole: state.demoRole,
      }),
    }
  )
);

export default useUiStore;
