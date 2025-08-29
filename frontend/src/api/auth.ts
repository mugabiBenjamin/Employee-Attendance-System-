import { api } from './index';
import { store } from '@/store';
import { clearAuth, setAuth } from '@/store/slices/authSlice';
import type { Permission, User } from './types';
import { enumsApi } from '@/api/enums';

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

    const { access_token, refresh_token, token_type } = response.data;

    // Store tokens in localStorage
    localStorage.setItem('access_token', access_token);
    localStorage.setItem('refresh_token', refresh_token);

    // Set Authorization header for immediate use
    api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;

    // Get user profile
    const user = await authApi.getCurrentUser();

    // Dispatch setAuth to update Redux store
    const loginResponse: LoginResponse = { access_token, refresh_token, token_type, user };
    store.dispatch(setAuth(loginResponse));

    // Log for debugging
    console.log("Login - User Permissions:", user.permissions);

    return loginResponse;
  },

  getCurrentUser: async (): Promise<User> => {
    try {
      const response = await api.get<UserResponse>('/auth/me');
      let permissions: Permission[] = response.data.permissions as Permission[] ?? [];

      // Check if permissions include 'all_permissions' and expand if necessary
      if (permissions.includes('all_permissions')) {
        try {
          const allPermissions = await enumsApi.getPermissions();
          console.log("Expanding 'all_permissions' to:", allPermissions);
          permissions = allPermissions;
        } catch (error) {
          console.error("Failed to fetch all permissions for 'all_permissions' expansion:", error);
          // Fallback to original permissions to avoid breaking the app
          permissions = response.data.permissions as Permission[] ?? [];
        }
      }

      const user: User = {
        id: response.data.user_id,
        email: response.data.email,
        first_name: response.data.first_name,
        last_name: response.data.last_name,
        roles: response.data.roles,
        permissions,
        is_active: true,
      };

      // Log for debugging
      console.log("getCurrentUser - User Permissions:", user.permissions);

      return user;
    } catch (error) {
      console.error("Failed to fetch current user:", error);
      throw new Error("Unable to fetch current user");
    }
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
      // Always clear tokens and Redux state
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      delete api.defaults.headers.common['Authorization'];
      store.dispatch(clearAuth()); // Clear Redux auth state
    }
  },
};