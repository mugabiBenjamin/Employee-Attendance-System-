import { api } from './index';
import type { AuthResponse, User } from './types';

interface LoginCredentials {
  email: string;
  password: string;
}

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<AuthResponse & { user: User }> => {
    const response = await api.post<AuthResponse>('/auth/token', new URLSearchParams({
      username: credentials.email,
      password: credentials.password,
    }), {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    // Store the access token in the api client headers
    const { access_token } = response.data;
    api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;

    const user = await authApi.getCurrentUser();
    return { ...response.data, user };
  },

  getCurrentUser: async (): Promise<User> => {
    const response = await api.get<User>('/auth/me');
    return response.data;
  },

  refreshToken: async (refreshToken: string): Promise<AuthResponse> => {
    const response = await api.post<AuthResponse>('/auth/refresh', { refresh_token: refreshToken });
    // Update the access token after refresh
    const { access_token } = response.data;
    api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
    return response.data;
  },

  logout: async (): Promise<void> => {
    await api.post('/auth/logout');
    // Clear the Authorization header on logout
    delete api.defaults.headers.common['Authorization'];
  },
};