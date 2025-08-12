export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  roles: string[];
  permissions: string[];
  department_id?: number;
  is_active: boolean;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AttendanceRecord {
  date: string;
  id: number;
  user_id: number;
  clock_in: string;
  clock_out?: string;
  status: string;
  created_at: string;
}

export interface TimeCorrection {
  id: number;
  attendance_record_id: number;
  corrected_clock_in?: string;
  corrected_clock_out?: string;
  reason: string;
  status: string;
  created_at: string;
}

export interface Department {
  id: number;
  name: string;
  description?: string;
  is_active: boolean;
}

export interface EmergencyContact {
  id: number;
  user_id: number;
  name: string;
  relationship: string;
  phone: string;
  email?: string;
  address?: string;
}

export interface EmployeeHierarchy {
  id: number;
  employee_id: number;
  manager_id: number;
}

export interface ShiftPattern {
  id: number;
  name: string;
  start_time: string;
  end_time: string;
  days: string[];
}

export interface SystemLog {
  id: number;
  user_id?: number;
  action: string;
  table_name: string;
  record_id?: number;
  created_at: string;
}

export interface UserRole {
  user_id: number;
  role: string;
}

export interface UserDepartment {
  user_id: number;
  department_id: number;
  is_primary: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
}

export interface AttendanceSummary {
  total_hours: number;
  overtime_hours: number;
  leave_balance: number;
  pending_requests: number;
  team_present?: number;
}