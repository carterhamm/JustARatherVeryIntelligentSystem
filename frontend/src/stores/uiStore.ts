import { create } from 'zustand';

interface UIState {
  sidebarOpen: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  isThinking: boolean;
  jarvisActivity: number;
  wsConnected: boolean;
  isOnline: boolean;
  theme: 'dark' | 'light';

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setIsListening: (listening: boolean) => void;
  setIsSpeaking: (speaking: boolean) => void;
  setIsThinking: (thinking: boolean) => void;
  setJarvisActivity: (activity: number) => void;
  setWsConnected: (connected: boolean) => void;
  setIsOnline: (online: boolean) => void;
  setTheme: (theme: 'dark' | 'light') => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  isListening: false,
  isSpeaking: false,
  isThinking: false,
  jarvisActivity: 0,
  wsConnected: false,
  isOnline: typeof navigator !== 'undefined' ? navigator.onLine : true,
  theme: 'dark',

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setIsListening: (listening) => set({ isListening: listening }),
  setIsSpeaking: (speaking) => set({ isSpeaking: speaking }),
  setIsThinking: (thinking) => set({ isThinking: thinking }),
  setJarvisActivity: (activity) => set({ jarvisActivity: Math.max(0, Math.min(1, activity)) }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  setIsOnline: (online) => set({ isOnline: online }),
  setTheme: (theme) => set({ theme }),
}));

// Listen for browser online/offline events
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => useUIStore.getState().setIsOnline(true));
  window.addEventListener('offline', () => useUIStore.getState().setIsOnline(false));
}
