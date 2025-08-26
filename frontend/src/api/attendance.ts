import { api } from './index';
import type { AttendanceRecord, PaginatedResponse, TimeCorrection, AttendanceSummary,CorrectionStatus } from './types';

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
  original_clock_in?: string;
  original_clock_out?: string;
  reason: string;
  status?: CorrectionStatus;
}

interface AttendanceSummaryQuery {
  department_id?: number;
  start_date?: string;
  end_date?: string;
  is_active?: boolean;
  skip?: number;
  limit?: number;
}

interface GenerateSummaryRequest {
  user_id: number;
  attendance_summary_date: string;
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
    const response = await api.get<AttendanceSummary>(`/attendance-summary/${user_id}`);
    return response.data;
  },

  getAllSummaries: async (query: AttendanceSummaryQuery): Promise<PaginatedResponse<AttendanceSummary>> => {
    const response = await api.get<PaginatedResponse<AttendanceSummary>>('/attendance-summary', { params: query });
    return response.data;
  },

  generateSummary: async (data: GenerateSummaryRequest): Promise<AttendanceSummary> => {
    const response = await api.post<AttendanceSummary>('/attendance-summary/generate', data);
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