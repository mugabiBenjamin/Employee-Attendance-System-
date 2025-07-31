import { api } from './index';
import type { PaginatedResponse, ShiftPattern } from './types';

interface ShiftQuery {
  page?: number;
  limit?: number;
}

interface ShiftPatternData {
  name: string;
  start_time: string;
  end_time: string;
  days: string[];
}

export const shiftsApi = {
  getShiftPatterns: async (query: ShiftQuery): Promise<PaginatedResponse<ShiftPattern>> => {
    const response = await api.get<PaginatedResponse<ShiftPattern>>('/shift-patterns', { params: query });
    return response.data;
  },

  createShiftPattern: async (data: ShiftPatternData): Promise<ShiftPattern> => {
    const response = await api.post<ShiftPattern>('/shift-patterns', data);
    return response.data;
  },

  updateShiftPattern: async (id: number, data: ShiftPatternData): Promise<ShiftPattern> => {
    const response = await api.put<ShiftPattern>(`/shift-patterns/${id}`, data);
    return response.data;
  },

  deleteShiftPattern: async (id: number): Promise<void> => {
    await api.delete(`/shift-patterns/${id}`);
  },
};