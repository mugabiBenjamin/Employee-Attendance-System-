import {
  type SystemAction,
  type AttendanceStatus,
  type LeaveRequestStatus,
  type LeaveType,
  type CorrectionStatus,
  type EmployeeType,
  type ShiftType,
  type Permission
} from "./enums";

/** =========================
 *  CORE MODELS
 *  ========================= */

export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  roles: string[];
  permissions: Permission[];
  department_id?: number;
  is_active: boolean;
  employee_type?: EmployeeType;
  created_at?: string;
  updated_at?: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RefreshTokenResponse {
  access_token: string;
  token_type: string;
}

/** =========================
 *  ATTENDANCE & TIME TRACKING
 *  ========================= */
export interface AttendanceRecord {
  attendance_id: number;
  date: string;
  user_id: number;
  clock_in: string;
  clock_out?: string;
  status: AttendanceStatus;
  created_at: string;
  updated_at?: string;
}

export interface AttendanceSummary {
  total_hours: number;
  overtime_hours: number;
  leave_balance: number;
  pending_requests: number;
  team_present?: number;
}

export interface TimeCorrection {
  time_correction_id: number;
  attendance_id: number;
  corrected_clock_in?: string;
  corrected_clock_out?: string;
  reason: string;
  status: CorrectionStatus;
  created_at: string;
  updated_at?: string;
}

/** =========================
 *  LEAVE MANAGEMENT
 *  ========================= */
export interface LeaveRequest {
  leave_request_id: number;
  user_id: number;
  start_date: string;
  end_date: string;
  leave_type: LeaveType;
  status: LeaveRequestStatus;
  reason?: string;
  created_at: string;
}

/** =========================
 *  DEPARTMENTS & ROLES
 *  ========================= */
export interface Department {
  department_id: number;
  name: string;
  description?: string;
  is_active: boolean;
}

export interface UserDepartment {
  user_id: number;
  department_id: number;
  is_primary: boolean;
}

export interface Role {
  role_id: number;
  name: string;
  description?: string;
}

export interface UserRole {
  user_id: number;
  role_id: number;
}

/** =========================
 *  EMERGENCY CONTACTS
 *  ========================= */
export interface EmergencyContact {
  emergency_contact_id: number;
  user_id: number;
  name: string;
  relationship: string;
  phone: string;
  email?: string;
  address?: string;
}

/** =========================
 *  EMPLOYEE HIERARCHY
 *  ========================= */
export interface EmployeeHierarchy {
  hierarchy_id: number;
  employee_id: number;
  manager_id: number;
}

/** =========================
 *  SHIFTS
 *  ========================= */
export interface ShiftPattern {
  shift_pattern_id: number;
  name: string;
  start_time: string;
  end_time: string;
  days: string[];
  shift_type?: ShiftType;
}

export interface ShiftAssignment {
  shift_assignment_id: number;
  shift_pattern_id: number;
  user_id: number;
  start_date: string;
  end_date?: string;
}

/** =========================
 *  SYSTEM LOGS
 *  ========================= */
export interface SystemLog {
  system_log_id: number;
  user_id?: number;
  action: SystemAction;
  table_name: string;
  record_id?: number;
  created_at: string;
}

/** =========================
 *  API RESPONSE WRAPPERS
 *  ========================= */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
}

export interface ApiError {
  detail: string;
  status_code?: number;
}
