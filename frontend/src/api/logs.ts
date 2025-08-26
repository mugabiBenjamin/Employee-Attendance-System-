import { api } from './index';
import type { PaginatedResponse, SystemLog } from './types';

interface LogQuery {
  page?: number;
  limit?: number;
  user_id?: number;
  action?: string;
  table_name?: string;
  start_date?: string;
  end_date?: string;
  record_id?: number;
}

export const logsApi = {
  getLogs: async (query: LogQuery): Promise<PaginatedResponse<SystemLog>> => {
    const response = await api.get<PaginatedResponse<SystemLog>>('/system-logs', { params: query });
    return response.data;
  },
};