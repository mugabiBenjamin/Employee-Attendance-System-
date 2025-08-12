import { createSlice } from '@reduxjs/toolkit';
import type { PayloadAction } from '@reduxjs/toolkit';
import type { AttendanceRecord, PaginatedResponse } from '@/api/types';

interface AttendanceState {
  records: AttendanceRecord[];
  summary: { total_hours: number; overtime_hours: number; leave_balance: number; pending_requests: number } | null;
  history: PaginatedResponse<AttendanceRecord> | null;
}

const initialState: AttendanceState = {
  records: [],
  summary: null,
  history: null,
};

const attendanceSlice = createSlice({
  name: 'attendance',
  initialState,
  reducers: {
    setRecords: (state, action: PayloadAction<AttendanceRecord[]>) => {
      state.records = action.payload;
    },
    setSummary: (state, action: PayloadAction<AttendanceState['summary']>) => {
      state.summary = action.payload;
    },
    setHistory: (state, action: PayloadAction<PaginatedResponse<AttendanceRecord>>) => {
      state.history = action.payload;
    },
  },
});

export const { setRecords, setSummary, setHistory } = attendanceSlice.actions;
export default attendanceSlice.reducer;