// CORE MODELS
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

// ATTENDANCE & TIME TRACKING
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

// LEAVE MANAGEMENT
export interface LeaveRequest {
  leave_request_id: number;
  user_id: number;
  start_date: string;
  end_date: string;
  leave_type: LeaveType;
  status: LeaveRequestStatus;
  reason?: string;
  created_at: string;
  updated_at?: string;
}

export interface LeaveBalance {
  leave_balance_id: number;
  user_id: number;
  leave_type: LeaveType;
  balance: number;
  used: number;
  accrued: number;
  created_at: string;
  updated_at?: string;
}

export interface LeavePolicy {
  leave_policy_id: number;
  name: string;
  description?: string;
  leave_type: LeaveType;
  max_days: number;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface LeaveApproval {
  approval_id: number;
  leave_request_id: number;
  approver_id: number;
  status: LeaveRequestStatus;
  comments?: string;
  created_at: string;
  updated_at?: string;
}

// DEPARTMENTS & ROLES
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
  permissions: Permission[];
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface UserRole {
  user_id: number;
  role_id: number;
}

// EMERGENCY CONTACTS
export interface EmergencyContact {
  emergency_contact_id: number;
  user_id: number;
  name: string;
  relationship: string;
  phone: string;
  email?: string;
  address?: string;
}

// EMPLOYEE HIERARCHY
export interface EmployeeHierarchy {
  hierarchy_id: number;
  employee_id: number;
  manager_id: number;
}

// SHIFTS
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

// SYSTEM LOGS
export interface SystemLog {
  system_log_id: number;
  user_id?: number;
  action: SystemAction;
  table_name: string;
  record_id?: number;
  created_at: string;
}

// OVERTIME RECORDS
export interface OvertimeRecord {
  overtime_id: number;
  user_id: number;
  date: string;
  hours: number;
  reason: string;
  status: OvertimeStatus;
  created_at: string;
  updated_at?: string;
}

// HOLIDAY CALENDAR
export interface Holiday {
  holiday_id: number;
  name: string;
  date: string;
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

// API RESPONSE WRAPPERS
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

// Enum value types
export type AttendanceStatus =
  | 'present'
  | 'absent'
  | 'late'
  | 'early_departure'
  | 'on_leave'
  | 'half_day'
  | 'sick';

export type LeaveRequestStatus =
  | 'draft'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'cancelled'
  | 'completed';

export type LeaveType =
  | 'annual'
  | 'sick'
  | 'maternity'
  | 'paternity'
  | 'emergency'
  | 'unpaid'
  | 'casual'
  | 'compensatory'
  | 'bereavement'
  | 'leave_of_absence'
  | 'public_holiday';

export type EmployeeType =
  | 'full_time'
  | 'part_time'
  | 'contract'
  | 'intern'
  | 'temporary'
  | 'all';

export type Permission = string; // Dynamic list from backend

export type PermissionGroup =
  | 'employee'
  | 'manager'
  | 'hr'
  | 'admin'
  | 'super_admin';

export type SystemAction =
  | 'INSERT'
  | 'UPDATE'
  | 'DELETE'
  | 'LOGIN'
  | 'LOGOUT'
  | 'CLOCK_IN'
  | 'CLOCK_OUT'
  | 'PASSWORD_CHANGE'
  | 'PROFILE_UPDATE'
  | 'DATA_EXPORT'
  | 'DATA_IMPORT'
  | 'ASSIGN_ROLE'
  | 'REVOKE_ROLE'
  | 'VIEW_REPORT'
  | 'GENERATE_REPORT'
  | 'APPROVE_LEAVE'
  | 'REJECT_LEAVE'
  | 'CREATE_DEPARTMENT'
  | 'UPDATE_DEPARTMENT'
  | 'DELETE_DEPARTMENT'
  | 'CREATE_ROLE'
  | 'UPDATE_ROLE'
  | 'DELETE_ROLE'
  | 'TOKEN_REFRESH'
  | 'CREATE_OVERTIME_RECORD'
  | 'UPDATE_OVERTIME_RECORD'
  | 'APPROVE_OVERTIME_RECORD'
  | 'DELETE_OVERTIME_RECORD'
  | 'CREATE_LEAVE_REQUEST'
  | 'UPDATE_LEAVE_REQUEST'
  | 'DELETE_LEAVE_REQUEST'
  | 'APPROVE_LEAVE_REQUEST'
  | 'UPDATE_LEAVE_APPROVAL'
  | 'DELETE_LEAVE_APPROVAL'
  | 'UPDATE_LEAVE_BALANCE'
  | 'CREATE_LEAVE_POLICY'
  | 'UPDATE_LEAVE_POLICY'
  | 'DELETE_LEAVE_POLICY'
  | 'CREATE_HOLIDAY'
  | 'UPDATE_HOLIDAY'
  | 'DELETE_HOLIDAY'
  | 'CREATE_TIME_CORRECTION'
  | 'UPDATE_TIME_CORRECTION'
  | 'DELETE_TIME_CORRECTION'
  | 'CREATE_EMERGENCY_CONTACT'
  | 'UPDATE_EMERGENCY_CONTACT'
  | 'DELETE_EMERGENCY_CONTACT'
  | 'CREATE_HIERARCHY'
  | 'UPDATE_HIERARCHY'
  | 'DELETE_HIERARCHY'
  | 'CREATE_SHIFT_ASSIGNMENT'
  | 'UPDATE_SHIFT_ASSIGNMENT'
  | 'DELETE_SHIFT_ASSIGNMENT'
  | 'CREATE_SHIFT_PATTERN'
  | 'UPDATE_SHIFT_PATTERN'
  | 'DELETE_SHIFT_PATTERN'
  | 'CREATE_USER_DEPARTMENT'
  | 'UPDATE_USER_DEPARTMENT'
  | 'DELETE_USER_DEPARTMENT'
  | 'DEFINE_WORKFLOW'
  | 'DELETE_SYSTEM_LOG';

export type CorrectionStatus =
  | 'draft'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'cancelled'
  | 'completed';

export type OvertimeStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'cancelled'
  | 'completed';

export type ShiftType =
  | 'morning'
  | 'afternoon'
  | 'night'
  | 'flexible'
  | 'split';

export type RoleName =
  | 'employee'
  | 'manager'
  | 'hr'
  | 'admin'
  | 'super_admin';

// API Response types
export interface PermissionGroups {
  [key: string]: Permission[];
}

export interface AllEnumsResponse {
  attendanceStatuses: AttendanceStatus[];
  leaveRequestStatuses: LeaveRequestStatus[];
  leaveTypes: LeaveType[];
  employeeTypes: EmployeeType[];
  permissions: Permission[];
  permissionGroups: PermissionGroups;
}

// Option types for dropdowns/selects
export interface EnumOption<T = string> {
  value: T;
  label: string;
}

// Utility types for enum operations
export interface EnumState<T> {
  data: T[];
  isLoading: boolean;
  error: string | null;
}

export interface AllEnumsState {
  attendanceStatuses: EnumState<AttendanceStatus>;
  leaveRequestStatuses: EnumState<LeaveRequestStatus>;
  leaveTypes: EnumState<LeaveType>;
  employeeTypes: EnumState<EmployeeType>;
  permissions: EnumState<Permission>;
  permissionGroups: {
    data: PermissionGroups;
    isLoading: boolean;
    error: string | null;
  };
}