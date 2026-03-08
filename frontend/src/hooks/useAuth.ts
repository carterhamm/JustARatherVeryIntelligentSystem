import { useCallback } from 'react';
import { useAuthStore, User } from '@/stores/authStore';
import { api } from '@/services/api';
import { createPasskey, authenticatePasskey } from '@/utils/webauthn';

interface AuthResponse {
  user: User;
  access_token: string;
  refresh_token: string;
}

interface TOTPRequiredResponse {
  needs_totp: true;
  totp_token: string;
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

  const passkeyRegister = useCallback(async (email: string, username: string, fullName?: string, setupToken?: string) => {
    // Step 1: Get registration options from server
    const options = await api.post<any>('/auth/register/begin', {
      email,
      username,
      full_name: fullName,
      setup_token: setupToken,
    });

    // Step 2: Create passkey in browser
    const credential = await createPasskey(options);

    // Step 3: Complete registration on server
    const response = await api.post<AuthResponse>('/auth/register/complete', {
      email,
      username,
      full_name: fullName,
      credential,
      setup_token: setupToken,
    });

    storeLogin(response.user, response.access_token, response.refresh_token);
    return response.user;
  }, [storeLogin]);

  const passkeyLogin = useCallback(async (identifier: string): Promise<User | TOTPRequiredResponse> => {
    // Step 1: Get authentication options from server
    const options = await api.post<any>('/auth/login/begin', { identifier });

    // Step 2: Authenticate with passkey in browser
    const credential = await authenticatePasskey(options);

    // Step 3: Complete authentication on server
    const response = await api.post<AuthResponse | TOTPRequiredResponse>('/auth/login/complete', {
      identifier,
      credential,
    });

    // Check if TOTP is required
    if ('needs_totp' in response && response.needs_totp) {
      return response as TOTPRequiredResponse;
    }

    const authResp = response as AuthResponse;
    storeLogin(authResp.user, authResp.access_token, authResp.refresh_token);
    return authResp.user;
  }, [storeLogin]);

  const verifyTOTPLogin = useCallback(async (totpToken: string, code: string) => {
    const response = await api.post<AuthResponse>('/auth/login/totp-verify', {
      totp_token: totpToken,
      code,
    });
    storeLogin(response.user, response.access_token, response.refresh_token);
    return response.user;
  }, [storeLogin]);

  const getTOTPStatus = useCallback(async (): Promise<{ totp_enabled: boolean }> => {
    return api.get<{ totp_enabled: boolean }>('/auth/totp/status');
  }, []);

  const setupTOTP = useCallback(async (): Promise<{ secret: string; otpauth_uri: string }> => {
    return api.post<{ secret: string; otpauth_uri: string }>('/auth/totp/setup');
  }, []);

  const enableTOTP = useCallback(async (code: string, secret: string): Promise<void> => {
    const baseUrl = import.meta.env.VITE_API_URL || '/api/v1';
    const token = useAuthStore.getState().token;
    const resp = await fetch(`${baseUrl}/auth/totp/enable`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'x-totp-secret': secret,
      },
      body: JSON.stringify({ code }),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to enable TOTP');
    }
  }, []);

  const disableTOTP = useCallback(async (code: string): Promise<void> => {
    await api.post('/auth/totp/disable', { code });
  }, []);

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
    verifyTOTPLogin,
    getTOTPStatus,
    setupTOTP,
    enableTOTP,
    disableTOTP,
  };
}
