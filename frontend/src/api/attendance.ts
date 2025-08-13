import { api } from './index';
import type { AttendanceRecord, PaginatedResponse, TimeCorrection } from './types';

// Define interfaces for request payloads
interface ClockInOutRequest {
  type: 'in' | 'out';
}

interface AttendanceQuery {
  user_id?: number;
  page?: number;
  limit?: number;
  start_date?: string;
  end_date?: string;
}

interface TimeCorrectionRequest {
  attendance_record_id: number;
  corrected_clock_in?: string;
  corrected_clock_out?: string;
  reason: string;
}

// Define interface for response payloads
interface AttendanceSummary {
  total_hours: number;
  overtime_hours: number;
  leave_balance: number;
  pending_requests: number;
  team_present?: number;
}

export const attendanceApi = {
  clockInOut: async (data: ClockInOutRequest): Promise<AttendanceRecord> => {
    const response = await api.post<AttendanceRecord>('/attendance-records/clock', data);
    return response.data;
  },

  getHistory: async (query: AttendanceQuery): Promise<PaginatedResponse<AttendanceRecord>> => {
    const response = await api.get<PaginatedResponse<AttendanceRecord>>('/attendance-records/history', { params: query });
    return response.data;
  },

  getSummary: async (user_id: number): Promise<AttendanceSummary> => {
    const response = await api.get<AttendanceSummary>('/attendance-records/summary', { params: { user_id } });
    return response.data;
  },

  requestTimeCorrection: async (data: TimeCorrectionRequest): Promise<TimeCorrection> => {
    const response = await api.post<TimeCorrection>('/attendance-records/time-correction', data);
    return response.data;
  },

  exportAttendance: async (format: 'csv' | 'pdf', query: AttendanceQuery): Promise<Blob> => {
    const response = await api.get(`/attendance-records/export/${format}`, { params: query, responseType: 'blob' });
    return response.data;
  },
};