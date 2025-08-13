// System actions
export type SystemAction =
  | "INSERT"
  | "UPDATE"
  | "DELETE"
  | "LOGIN"
  | "LOGOUT"
  | "CLOCK_IN"
  | "CLOCK_OUT"
  | "password_change"
  | "profile_update"
  | "data_export"
  | "data_import"
  | "assign_role"
  | "revoke_role"
  | "view_report"
  | "approve_leave"
  | "reject_leave"
  | "create_department"
  | "delete_department";

// Attendance status
export type AttendanceStatus =
  | "present"
  | "absent"
  | "late"
  | "early_departure"
  | "on_leave"
  | "half_day"
  | "sick";

// Leave request status
export type LeaveRequestStatus =
  | "draft"
  | "under_review"
  | "approved"
  | "rejected"
  | "cancelled"
  | "completed";

// Leave type
export type LeaveType =
  | "annual"
  | "sick"
  | "maternity"
  | "paternity"
  | "emergency"
  | "unpaid"
  | "casual"
  | "compensatory"
  | "bereavement"
  | "leave_of_absence"
  | "public_holiday";

// Time correction status
export type CorrectionStatus =
  | "draft"
  | "under_review"
  | "approved"
  | "rejected"
  | "cancelled"
  | "completed";

// Employee type
export type EmployeeType =
  | "full_time"
  | "part_time"
  | "contract"
  | "intern"
  | "temporary";

// Shift type
export type ShiftType =
  | "morning"
  | "afternoon"
  | "night"
  | "flexible"
  | "split";

// Permission set
export const Permission = {
  // Employee permissions
  CLOCK_IN: "clock_in",
  CLOCK_OUT: "clock_out",
  REQUEST_LEAVE: "request_leave",
  VIEW_LEAVE_BALANCE: "view_leave_balance",
  VIEW_OWN_ATTENDANCE: "view_own_attendance",

  // Manager permissions
  APPROVE_LEAVE: "approve_leave",
  MANAGE_OVERTIME: "manage_overtime",
  GENERATE_REPORTS: "generate_reports",
  VIEW_TEAM_ATTENDANCE: "view_team_attendance",

  // HR permissions
  MANAGE_EMPLOYEES: "manage_employees",
  CREATE_USER: "create_user",
  VIEW_USER: "view_user",
  UPDATE_USER: "update_user",
  DELETE_USER: "delete_user",
  VIEW_ALL_ATTENDANCE: "view_all_attendance",
  MANAGE_LEAVE_POLICIES: "manage_leave_policies",
  GENERATE_COMPLIANCE_REPORTS: "generate_compliance_reports",

  // Admin permissions
  VIEW_LOGS: "view_logs",
  MANAGE_ROLES: "manage_roles",
  CREATE_USER_ROLE: "create_user_role",
  VIEW_USER_ROLE: "view_user_role",
  UPDATE_USER_ROLE: "update_user_role",
  DELETE_USER_ROLE: "delete_user_role",
  MANAGE_USERS: "manage_users",
  MANAGE_DEPARTMENTS: "manage_departments",
  CREATE_USER_DEPARTMENT: "create_user_department",
  VIEW_USER_DEPARTMENT: "view_user_department",
  UPDATE_USER_DEPARTMENT: "update_user_department",
  DELETE_USER_DEPARTMENT: "delete_user_department",
  SYSTEM_CONFIGURATION: "system_configuration",

  // Super Admin
  ALL_PERMISSIONS: "all_permissions",
} as const;

// Derive a string union type from the runtime object
export type Permission = typeof Permission[keyof typeof Permission];