import type { Permission } from './enums';
import { api } from './index';
import type { User } from './types';

// Define request payload interfaces
interface LoginCredentials {
  email: string;
  password: string;
}

// Define response interfaces
interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

interface LoginResponse extends AuthResponse {
  user: User;
}

interface UserResponse {
  user_id: number;
  email: string;
  first_name: string;
  last_name: string;
  job_title: string | null;
  roles: string[];
  permissions: string[];
}

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<LoginResponse> => {
    const response = await api.post<AuthResponse>('/auth/token', new URLSearchParams({
      username: credentials.email,
      password: credentials.password,
    }), {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    const { access_token, refresh_token } = response.data;

    // Store tokens in localStorage
    localStorage.setItem('access_token', access_token);
    localStorage.setItem('refresh_token', refresh_token);

    // Set Authorization header for immediate use
    api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;

    // Get user profile
    const user = await authApi.getCurrentUser();

    return { ...response.data, user };
  },

  getCurrentUser: async (): Promise<User> => {
    const response = await api.get<UserResponse>('/auth/me');

    return {
      id: response.data.user_id,
      email: response.data.email,
      first_name: response.data.first_name,
      last_name: response.data.last_name,
      roles: response.data.roles,
      permissions: response.data.permissions as Permission[],
      is_active: true,
    };
  },

  refreshToken: async (refreshToken: string): Promise<AuthResponse> => {
    const response = await api.post<AuthResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });

    const { access_token, refresh_token: new_refresh_token } = response.data;

    // Update stored tokens
    localStorage.setItem('access_token', access_token);
    localStorage.setItem('refresh_token', new_refresh_token);

    // Update Authorization header
    api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;

    return response.data;
  },

  logout: async (): Promise<void> => {
    try {
      await api.post('/auth/logout');
    } finally {
      // Always clear tokens, even if logout request fails
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      delete api.defaults.headers.common['Authorization'];
    }
  },
};