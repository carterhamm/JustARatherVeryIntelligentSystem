import { create } from 'zustand';
import { api } from '@/services/api';

export type ModelProvider = 'claude' | 'gemini' | 'stark_protocol';

interface SettingsState {
  modelPreference: ModelProvider;
  voiceEnabled: boolean;
  use24HourTime: boolean;
  isLoading: boolean;

  setModelPreference: (provider: ModelProvider) => void;
  setVoiceEnabled: (enabled: boolean) => void;
  setUse24HourTime: (enabled: boolean) => void;
  loadPreferences: () => Promise<void>;
  savePreferences: () => Promise<void>;
}

const STORAGE_KEY = 'jarvis-model-preference';
const VOICE_STORAGE_KEY = 'jarvis-voice-enabled';
const TIME_FORMAT_KEY = 'jarvis-24h-time';

function getStoredPreference(): ModelProvider {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && ['claude', 'gemini', 'stark_protocol'].includes(stored)) {
      return stored as ModelProvider;
    }
  } catch {
    // ignore
  }
  return 'gemini';
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  modelPreference: getStoredPreference(),
  voiceEnabled: localStorage.getItem(VOICE_STORAGE_KEY) === 'true',
  use24HourTime: localStorage.getItem(TIME_FORMAT_KEY) === 'true',
  isLoading: false,

  setUse24HourTime: (enabled: boolean) => {
    localStorage.setItem(TIME_FORMAT_KEY, String(enabled));
    set({ use24HourTime: enabled });
  },

  setVoiceEnabled: (enabled: boolean) => {
    localStorage.setItem(VOICE_STORAGE_KEY, String(enabled));
    set({ voiceEnabled: enabled });
    get().savePreferences();
  },

  setModelPreference: (provider: ModelProvider) => {
    localStorage.setItem(STORAGE_KEY, provider);
    set({ modelPreference: provider });
    // Fire-and-forget save to server
    get().savePreferences();
  },

  loadPreferences: async () => {
    set({ isLoading: true });
    try {
      const prefs = await api.get<{ model_preference?: string }>('/auth/me/preferences');
      if (prefs.model_preference) {
        const provider = prefs.model_preference as ModelProvider;
        localStorage.setItem(STORAGE_KEY, provider);
        set({ modelPreference: provider });
      }
    } catch {
      // Use local storage fallback
    } finally {
      set({ isLoading: false });
    }
  },

  savePreferences: async () => {
    const { modelPreference, voiceEnabled } = get();
    try {
      await api.put('/auth/me/preferences', {
        model_preference: modelPreference,
        voice_enabled: voiceEnabled,
      });
    } catch {
      // Non-critical — local storage is the primary store
    }
  },
}));
