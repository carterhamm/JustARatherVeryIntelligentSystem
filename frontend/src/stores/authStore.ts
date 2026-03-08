import { create } from 'zustand';

export interface User {
  id: string;
  email: string;
  username: string;
  full_name?: string;
  avatar?: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  setRefreshToken: (refreshToken: string | null) => void;
  login: (user: User, token: string, refreshToken: string) => void;
  logout: () => void;
}

const storedToken = localStorage.getItem('jarvis_token');
const storedRefreshToken = localStorage.getItem('jarvis_refresh_token');
const storedUser = localStorage.getItem('jarvis_user');

export const useAuthStore = create<AuthState>((set) => ({
  user: storedUser ? JSON.parse(storedUser) : null,
  token: storedToken,
  refreshToken: storedRefreshToken,
  isAuthenticated: !!storedToken,

  setUser: (user) => {
    if (user) {
      localStorage.setItem('jarvis_user', JSON.stringify(user));
    } else {
      localStorage.removeItem('jarvis_user');
    }
    set({ user });
  },

  setToken: (token) => {
    if (token) {
      localStorage.setItem('jarvis_token', token);
    } else {
      localStorage.removeItem('jarvis_token');
    }
    set({ token, isAuthenticated: !!token });
  },

  setRefreshToken: (refreshToken) => {
    if (refreshToken) {
      localStorage.setItem('jarvis_refresh_token', refreshToken);
    } else {
      localStorage.removeItem('jarvis_refresh_token');
    }
    set({ refreshToken });
  },

  login: (user, token, refreshToken) => {
    localStorage.setItem('jarvis_user', JSON.stringify(user));
    localStorage.setItem('jarvis_token', token);
    localStorage.setItem('jarvis_refresh_token', refreshToken);
    set({ user, token, refreshToken, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('jarvis_user');
    localStorage.removeItem('jarvis_token');
    localStorage.removeItem('jarvis_refresh_token');
    set({ user: null, token: null, refreshToken: null, isAuthenticated: false });
  },
}));
