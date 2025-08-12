import { api } from './index';
import type { PaginatedResponse, User, UserRole, UserDepartment } from './types';

interface UserQuery {
  page?: number;
  limit?: number;
}

interface CreateUserData {
  email: string;
  first_name: string;
  last_name: string;
  password?: string;
  department_id?: number;
}

interface UpdateUserData {
  email?: string;
  first_name?: string;
  last_name?: string;
  department_id?: number;
  is_active?: boolean;
}

export const usersApi = {
  getUsers: async (query: UserQuery): Promise<PaginatedResponse<User>> => {
    const response = await api.get<PaginatedResponse<User>>('/users', { params: query });
    return response.data;
  },

  createUser: async (data: CreateUserData): Promise<User> => {
    const response = await api.post<User>('/users', data);
    return response.data;
  },

  updateUser: async (id: number, data: UpdateUserData): Promise<User> => {
    const response = await api.put<User>(`/users/${id}`, data);
    return response.data;
  },

  deleteUser: async (id: number): Promise<void> => {
    await api.delete(`/users/${id}`);
  },

  assignRole: async (data: UserRole): Promise<UserRole> => {
    const response = await api.post<UserRole>('/user-roles', data);
    return response.data;
  },

  removeRole: async (user_id: number, role: string): Promise<void> => {
    await api.delete(`/user-roles/${user_id}/${role}`);
  },

  assignDepartment: async (data: UserDepartment): Promise<UserDepartment> => {
    const response = await api.post<UserDepartment>('/user-departments', data);
    return response.data;
  },

  removeDepartment: async (user_id: number, department_id: number): Promise<void> => {
    await api.delete(`/user-departments/${user_id}/${department_id}`);
  },
};