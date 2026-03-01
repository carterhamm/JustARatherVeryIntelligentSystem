import { create } from 'zustand';

interface UIState {
  sidebarOpen: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  isThinking: boolean;
  jarvisActivity: number;
  wsConnected: boolean;
  theme: 'dark' | 'light';

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setIsListening: (listening: boolean) => void;
  setIsSpeaking: (speaking: boolean) => void;
  setIsThinking: (thinking: boolean) => void;
  setJarvisActivity: (activity: number) => void;
  setWsConnected: (connected: boolean) => void;
  setTheme: (theme: 'dark' | 'light') => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  isListening: false,
  isSpeaking: false,
  isThinking: false,
  jarvisActivity: 0,
  wsConnected: false,
  theme: 'dark',

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setIsListening: (listening) => set({ isListening: listening }),
  setIsSpeaking: (speaking) => set({ isSpeaking: speaking }),
  setIsThinking: (thinking) => set({ isThinking: thinking }),
  setJarvisActivity: (activity) => set({ jarvisActivity: Math.max(0, Math.min(1, activity)) }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  setTheme: (theme) => set({ theme }),
}));
