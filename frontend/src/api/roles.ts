import { api } from './index';
import type { PaginatedResponse, Permission, Role } from './types';

interface RoleQuery {
    page?: number;
    limit?: number;
}

interface RoleData {
    name: string;
    description?: string;
    permissions?: Permission[];
}

export const rolesApi = {
    getRoles: async (query: RoleQuery): Promise<PaginatedResponse<Role>> => {
        const response = await api.get<PaginatedResponse<Role>>('/roles', { params: query });
        return response.data;
    },

    createRole: async (data: RoleData): Promise<Role> => {
        const response = await api.post<Role>('/roles', data);
        return response.data;
    },

    updateRole: async (id: number, data: RoleData): Promise<Role> => {
        const response = await api.put<Role>(`/roles/${id}`, data);
        return response.data;
    },

    deleteRole: async (id: number): Promise<void> => {
        await api.delete(`/roles/${id}`);
    },
};