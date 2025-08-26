import { api } from './index';
import type { PaginatedResponse, OvertimeRecord } from './types';

interface OvertimeQuery {
    user_id?: number;
    start_date?: string;
    end_date?: string;
    page?: number;
    limit?: number;
}

interface OvertimeRecordData {
    user_id: number;
    date: string;
    hours: number;
    reason: string;
}

export const overtimeApi = {
    getOvertimeRecords: async (query: OvertimeQuery): Promise<PaginatedResponse<OvertimeRecord>> => {
        const response = await api.get<PaginatedResponse<OvertimeRecord>>('/overtime-records', { params: query });
        return response.data;
    },

    createOvertimeRecord: async (data: OvertimeRecordData): Promise<OvertimeRecord> => {
        const response = await api.post<OvertimeRecord>('/overtime-records', data);
        return response.data;
    },

    updateOvertimeRecord: async (id: number, data: OvertimeRecordData): Promise<OvertimeRecord> => {
        const response = await api.put<OvertimeRecord>(`/overtime-records/${id}`, data);
        return response.data;
    },

    deleteOvertimeRecord: async (id: number): Promise<void> => {
        await api.delete(`/overtime-records/${id}`);
    },
};