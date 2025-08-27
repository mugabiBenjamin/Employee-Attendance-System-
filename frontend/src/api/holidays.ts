import { api } from './index';
import type { PaginatedResponse, Holiday } from './types';

interface HolidayQuery {
    year?: number;
    page?: number;
    limit?: number;
    search?: string;
}

interface HolidayData {
    name: string;
    date: string;
    description?: string;
}

export const holidaysApi = {
    getHolidays: async (query: HolidayQuery): Promise<PaginatedResponse<Holiday>> => {
        const response = await api.get<PaginatedResponse<Holiday>>('/holiday-calendar', { params: query });
        return response.data;
    },

    createHoliday: async (data: HolidayData): Promise<Holiday> => {
        const response = await api.post<Holiday>('/holiday-calendar', data);
        return response.data;
    },

    updateHoliday: async (id: number, data: HolidayData): Promise<Holiday> => {
        const response = await api.put<Holiday>(`/holiday-calendar/${id}`, data);
        return response.data;
    },

    deleteHoliday: async (id: number): Promise<void> => {
        await api.delete(`/holiday-calendar/${id}`);
    },


    async getHolidayById(id: number): Promise<Holiday> {
        const response = await api.get(`/holiday-calendar/${id}`);
        return response.data;
    }
};