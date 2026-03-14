import axios, { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '@/stores/authStore';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

export interface ApiResponse<T> {
  data: T;
  message?: string;
  status: number;
}

class ApiClient {
  private client: AxiosInstance;
  private isRefreshing = false;
  private refreshQueue: Array<{
    resolve: (token: string) => void;
    reject: (error: unknown) => void;
  }> = [];

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.client.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        const token = useAuthStore.getState().token;
        if (token && config.headers) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    this.client.interceptors.response.use(
      (response: AxiosResponse) => response,
      async (error) => {
        const originalRequest = error.config;

        const status = error.response?.status;

        // On 429 (rate limited), wait and retry once instead of failing
        if (status === 429 && !originalRequest._rateLimitRetry) {
          originalRequest._rateLimitRetry = true;
          await new Promise((r) => setTimeout(r, 2000));
          return this.client(originalRequest);
        }

        if (status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;

          if (this.isRefreshing) {
            return new Promise((resolve, reject) => {
              this.refreshQueue.push({ resolve, reject });
            }).then((token) => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              return this.client(originalRequest);
            });
          }

          this.isRefreshing = true;

          try {
            const refreshToken = useAuthStore.getState().refreshToken;
            if (!refreshToken) {
              throw new Error('No refresh token');
            }

            const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
              refresh_token: refreshToken,
            });

            const { access_token, refresh_token } = response.data;
            useAuthStore.getState().setToken(access_token);
            useAuthStore.getState().setRefreshToken(refresh_token);

            this.refreshQueue.forEach(({ resolve }) => resolve(access_token));
            this.refreshQueue = [];

            originalRequest.headers.Authorization = `Bearer ${access_token}`;
            return this.client(originalRequest);
          } catch (refreshError: any) {
            this.refreshQueue.forEach(({ reject }) => reject(refreshError));
            this.refreshQueue = [];
            // Only logout if refresh genuinely failed (not rate limited)
            const refreshStatus = refreshError?.response?.status;
            if (refreshStatus === 429) {
              // Rate limited — don't logout, just fail this request
              return Promise.reject(refreshError);
            }
            useAuthStore.getState().logout();
            window.location.href = '/login';
            return Promise.reject(refreshError);
          } finally {
            this.isRefreshing = false;
          }
        }

        return Promise.reject(error);
      }
    );
  }

  async get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
    const response = await this.client.get<T>(url, { params });
    return response.data;
  }

  async post<T>(url: string, data?: unknown): Promise<T> {
    const response = await this.client.post<T>(url, data);
    return response.data;
  }

  async put<T>(url: string, data?: unknown): Promise<T> {
    const response = await this.client.put<T>(url, data);
    return response.data;
  }

  async delete<T>(url: string): Promise<T> {
    const response = await this.client.delete<T>(url);
    return response.data;
  }

  async postFormData<T>(url: string, formData: FormData): Promise<T> {
    const response = await this.client.post<T>(url, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async getPreferences(): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>('/auth/me/preferences');
  }

  async updatePreferences(prefs: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.put<Record<string, unknown>>('/auth/me/preferences', prefs);
  }
}

export const api = new ApiClient();
