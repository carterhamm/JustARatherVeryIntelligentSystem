import { create } from 'zustand';

// Panel categories — only one panel per category can be open at a time
// "side_menu" = contacts, sessions, diagnostics, etc.
// "panel" = settings, model picker
type PanelCategory = 'side_menu' | 'panel' | null;

interface UIState {
  sidebarOpen: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  isThinking: boolean;
  jarvisActivity: number;
  wsConnected: boolean;
  isOnline: boolean;
  theme: 'dark' | 'light';
  activeOverlay: string | null;  // Currently open overlay panel name
  activeOverlayCategory: PanelCategory;

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setIsListening: (listening: boolean) => void;
  setIsSpeaking: (speaking: boolean) => void;
  setIsThinking: (thinking: boolean) => void;
  setJarvisActivity: (activity: number) => void;
  setWsConnected: (connected: boolean) => void;
  setIsOnline: (online: boolean) => void;
  setTheme: (theme: 'dark' | 'light') => void;
  openOverlay: (name: string, category: PanelCategory) => void;
  closeOverlay: (name?: string) => void;
}

export const useUIStore = create<UIState>((set, get) => ({
  sidebarOpen: true,
  isListening: false,
  isSpeaking: false,
  isThinking: false,
  jarvisActivity: 0,
  wsConnected: false,
  isOnline: typeof navigator !== 'undefined' ? navigator.onLine : true,
  theme: 'dark',
  activeOverlay: null,
  activeOverlayCategory: null,

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setIsListening: (listening) => set({ isListening: listening }),
  setIsSpeaking: (speaking) => set({ isSpeaking: speaking }),
  setIsThinking: (thinking) => set({ isThinking: thinking }),
  setJarvisActivity: (activity) => set({ jarvisActivity: Math.max(0, Math.min(1, activity)) }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  setIsOnline: (online) => set({ isOnline: online }),
  setTheme: (theme) => set({ theme }),

  // Mutual exclusivity: opening a side_menu closes any panel, and vice versa
  openOverlay: (name, category) => {
    const current = get();
    if (current.activeOverlay === name) {
      // Toggle off
      set({ activeOverlay: null, activeOverlayCategory: null });
    } else {
      // Close any conflicting overlay and open the new one
      set({ activeOverlay: name, activeOverlayCategory: category });
    }
  },
  closeOverlay: (name) => {
    const current = get();
    if (!name || current.activeOverlay === name) {
      set({ activeOverlay: null, activeOverlayCategory: null });
    }
  },
}));

/**
 * Hook for panels to use the mutual exclusivity system.
 * Usage: const { isOpen, toggle, close } = usePanelOverlay('settings', 'panel');
 */
export function usePanelOverlay(name: string, category: PanelCategory) {
  const activeOverlay = useUIStore((s) => s.activeOverlay);
  const openOverlay = useUIStore((s) => s.openOverlay);
  const closeOverlay = useUIStore((s) => s.closeOverlay);

  return {
    isOpen: activeOverlay === name,
    toggle: () => openOverlay(name, category),
    close: () => closeOverlay(name),
    open: () => openOverlay(name, category),
  };
}

// Listen for browser online/offline events
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => useUIStore.getState().setIsOnline(true));
  window.addEventListener('offline', () => useUIStore.getState().setIsOnline(false));
}
