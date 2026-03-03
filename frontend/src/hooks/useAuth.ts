import { useCallback } from 'react';
import { useAuthStore, User } from '@/stores/authStore';
import { api } from '@/services/api';
import { createPasskey, authenticatePasskey } from '@/utils/webauthn';

interface AuthResponse {
  user: User;
  access_token: string;
  refresh_token: string;
}

interface LookupResponse {
  exists: boolean;
  user_id?: string;
  username?: string;
}

export function useAuth() {
  const { user, token, isAuthenticated, login: storeLogin, logout: storeLogout, setToken, setRefreshToken } = useAuthStore();

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.post<AuthResponse>('/auth/login', {
      email,
      password,
    });
    storeLogin(response.user, response.access_token, response.refresh_token);
    return response.user;
  }, [storeLogin]);

  const register = useCallback(async (email: string, username: string, password: string) => {
    const response = await api.post<AuthResponse>('/auth/register', {
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

  // -- Passkey methods --

  const lookup = useCallback(async (identifier: string): Promise<LookupResponse> => {
    return api.post<LookupResponse>('/auth/lookup', { identifier });
  }, []);

  const passkeyRegister = useCallback(async (email: string, username: string, fullName?: string) => {
    // Step 1: Get registration options from server
    const options = await api.post<any>('/auth/register/begin', {
      email,
      username,
      full_name: fullName,
    });

    // Step 2: Create passkey in browser
    const credential = await createPasskey(options);

    // Step 3: Complete registration on server
    const response = await api.post<AuthResponse>('/auth/register/complete', {
      email,
      username,
      full_name: fullName,
      credential,
    });

    storeLogin(response.user, response.access_token, response.refresh_token);
    return response.user;
  }, [storeLogin]);

  const passkeyLogin = useCallback(async (identifier: string) => {
    // Step 1: Get authentication options from server
    const options = await api.post<any>('/auth/login/begin', { identifier });

    // Step 2: Authenticate with passkey in browser
    const credential = await authenticatePasskey(options);

    // Step 3: Complete authentication on server
    const response = await api.post<AuthResponse>('/auth/login/complete', {
      identifier,
      credential,
    });

    storeLogin(response.user, response.access_token, response.refresh_token);
    return response.user;
  }, [storeLogin]);

  return {
    user,
    token,
    isAuthenticated,
    login,
    register,
    logout,
    refreshToken: refreshTokenFn,
    lookup,
    passkeyRegister,
    passkeyLogin,
  };
}
