import { api } from './index';
import type {
    AttendanceStatus,
    LeaveRequestStatus,
    LeaveType,
    EmployeeType,
    Permission,
    PermissionGroups
} from './types';

export const enumsApi = {
    getAttendanceStatuses: async (): Promise<AttendanceStatus[]> => {
        const response = await api.get('/enums/attendance-status');
        return response.data;
    },

    getLeaveRequestStatuses: async (): Promise<LeaveRequestStatus[]> => {
        const response = await api.get('/enums/leave-request-status');
        return response.data;
    },

    getLeaveTypes: async (): Promise<LeaveType[]> => {
        const response = await api.get('/enums/leave-types');
        return response.data;
    },

    getEmployeeTypes: async (): Promise<EmployeeType[]> => {
        const response = await api.get('/enums/employee-types');
        return response.data;
    },

    getPermissions: async (): Promise<Permission[]> => {
        const response = await api.get('/enums/permissions');
        return response.data;
    },

    getPermissionGroups: async (): Promise<PermissionGroups> => {
        const response = await api.get('/enums/permission-groups');
        return response.data;
    },

    // Fetch all enums at once for initialization
    getAllEnums: async () => {
        const [
            attendanceStatuses,
            leaveRequestStatuses,
            leaveTypes,
            employeeTypes,
            permissions,
            permissionGroups
        ] = await Promise.all([
            enumsApi.getAttendanceStatuses(),
            enumsApi.getLeaveRequestStatuses(),
            enumsApi.getLeaveTypes(),
            enumsApi.getEmployeeTypes(),
            enumsApi.getPermissions(),
            enumsApi.getPermissionGroups()
        ]);

        return {
            attendanceStatuses,
            leaveRequestStatuses,
            leaveTypes,
            employeeTypes,
            permissions,
            permissionGroups
        };
    }
};