from sqlalchemy.dialects.postgresql import ENUM

# Enum definitions for PostgreSQL
attendance_status_enum = ENUM(
    'present', 'absent', 'late', 'early_departure', 'on_leave', 'half_day', 'sick',
    name='attendance_status'
)

leave_request_status_enum = ENUM(
    'draft', 'under_review', 'approved', 'rejected', 'cancelled', 'completed',
    name='leave_request_status'
)

leave_type_enum = ENUM(
    'annual', 'sick', 'maternity', 'paternity', 'emergency', 'unpaid', 'casual',
    'compensatory', 'bereavement', 'leave_of_absence', 'public_holiday',
    name='leave_type'
)

correction_status_enum = ENUM(
    'draft', 'under_review', 'approved', 'rejected', 'cancelled', 'completed',
    name='correction_status'
)

employee_type_enum = ENUM(
    'full_time', 'part_time', 'contract', 'intern', 'temporary',
    name='employee_type'
)

shift_type_enum = ENUM(
    'morning', 'afternoon', 'night', 'flexible', 'split',
    name='shift_type'
)

system_action_enum = ENUM(
    'INSERT', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT', 'CLOCK_IN', 'CLOCK_OUT',
    'password_change', 'profile_update', 'data_export', 'data_import',
    'assign_role', 'revoke_role', 'view_report', 'approve_leave',
    'reject_leave', 'create_department', 'delete_department',
    name='system_action'
)