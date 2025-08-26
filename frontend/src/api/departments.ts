import { api } from './index';
import type { Department, PaginatedResponse } from './types';

interface DepartmentQuery {
  page?: number;
  limit?: number;
  is_active?: boolean;
  supervisor_id?: number;
}

interface DepartmentData {
  name: string;
  description?: string;
  supervisor_id?: number;
  budget?: number;
  location?: string;
  is_active?: boolean;
}

export const departmentsApi = {
  getDepartments: async (query: DepartmentQuery): Promise<PaginatedResponse<Department>> => {
    const response = await api.get<PaginatedResponse<Department>>('/departments', { params: query });
    return response.data;
  },

  createDepartment: async (data: DepartmentData): Promise<Department> => {
    const response = await api.post<Department>('/departments', data);
    return response.data;
  },

  updateDepartment: async (id: number, data: DepartmentData): Promise<Department> => {
    const response = await api.put<Department>(`/departments/${id}`, data);
    return response.data;
  },

  deleteDepartment: async (id: number): Promise<void> => {
    await api.delete(`/departments/${id}`);
  },
};