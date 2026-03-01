import { useCallback } from 'react';
import { useAuthStore, User } from '@/stores/authStore';
import { api } from '@/services/api';

interface LoginResponse {
  user: User;
  access_token: string;
  refresh_token: string;
}

interface RegisterResponse {
  user: User;
  access_token: string;
  refresh_token: string;
}

export function useAuth() {
  const { user, token, isAuthenticated, login: storeLogin, logout: storeLogout, setToken, setRefreshToken } = useAuthStore();

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.post<LoginResponse>('/auth/login', {
      email,
      password,
    });
    storeLogin(response.user, response.access_token, response.refresh_token);
    return response.user;
  }, [storeLogin]);

  const register = useCallback(async (email: string, username: string, password: string) => {
    const response = await api.post<RegisterResponse>('/auth/register', {
      email,
      username,
      password,
    });
    storeLogin(response.user, response.access_token, response.refresh_token);
    return response.user;
  }, [storeLogin]);

  const logout = useCallback(() => {
    storeLogout();
  }, [storeLogout]);

  const refreshTokenFn = useCallback(async () => {
    const currentRefreshToken = useAuthStore.getState().refreshToken;
    if (!currentRefreshToken) {
      storeLogout();
      return;
    }
    try {
      const response = await api.post<{ access_token: string; refresh_token: string }>(
        '/auth/refresh',
        { refresh_token: currentRefreshToken }
      );
      setToken(response.access_token);
      setRefreshToken(response.refresh_token);
    } catch {
      storeLogout();
    }
  }, [storeLogout, setToken, setRefreshToken]);

  return {
    user,
    token,
    isAuthenticated,
    login,
    register,
    logout,
    refreshToken: refreshTokenFn,
  };
}
