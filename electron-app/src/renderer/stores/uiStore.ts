import { create } from 'zustand';
import type { Toast } from '../types';

type ActiveView = 'pipeline' | 'results' | 'settings';

interface UIState {
  activeView: ActiveView;
  sidebarCollapsed: boolean;
  toasts: Toast[];
  setActiveView: (view: ActiveView) => void;
  toggleSidebar: () => void;
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeView: 'pipeline',
  sidebarCollapsed: false,
  toasts: [],

  setActiveView: (view) => set({ activeView: view }),

  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  addToast: (toast) => {
    const id = crypto.randomUUID();
    const duration = toast.duration ?? 5000;
    set((state) => ({ toasts: [...state.toasts, { ...toast, id }] }));
    if (duration > 0) {
      setTimeout(() => {
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        }));
      }, duration);
    }
  },

  removeToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),
}));
