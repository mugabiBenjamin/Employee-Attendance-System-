import { api } from './index';
import type {
    AttendanceStatus,
    LeaveRequestStatus,
    LeaveType,
    EmployeeType,
    Permission,
    PermissionGroups,
} from './types';

export const enumsApi = {
    getAttendanceStatuses: async (): Promise<AttendanceStatus[]> => {
        try {
            const response = await api.get('/enums/attendance-status');
            return response.data;
        } catch (error) {
            console.error("Failed to fetch attendance statuses:", error);
            throw new Error("Unable to fetch attendance statuses");
        }
    },

    getLeaveRequestStatuses: async (): Promise<LeaveRequestStatus[]> => {
        try {
            const response = await api.get('/enums/leave-request-status');
            return response.data;
        } catch (error) {
            console.error("Failed to fetch leave request statuses:", error);
            throw new Error("Unable to fetch leave request statuses");
        }
    },

    getLeaveTypes: async (): Promise<LeaveType[]> => {
        try {
            const response = await api.get('/enums/leave-types');
            return response.data;
        } catch (error) {
            console.error("Failed to fetch leave types:", error);
            throw new Error("Unable to fetch leave types");
        }
    },

    getEmployeeTypes: async (): Promise<EmployeeType[]> => {
        try {
            const response = await api.get('/enums/employee-types');
            return response.data;
        } catch (error) {
            console.error("Failed to fetch employee types:", error);
            throw new Error("Unable to fetch employee types");
        }
    },

    getPermissions: async (): Promise<Permission[]> => {
        try {
            const response = await api.get('/enums/permissions');
            return response.data;
        } catch (error) {
            console.error("Failed to fetch permissions:", error);
            throw new Error("Unable to fetch permissions");
        }
    },

    getPermissionGroups: async (): Promise<PermissionGroups> => {
        try {
            const response = await api.get('/enums/permission-groups');
            return response.data;
        } catch (error) {
            console.error("Failed to fetch permission groups:", error);
            throw new Error("Unable to fetch permission groups");
        }
    },

    // Fetch all enums at once for initialization
    getAllEnums: async () => {
        try {
            const [
                attendanceStatuses,
                leaveRequestStatuses,
                leaveTypes,
                employeeTypes,
                permissions,
                permissionGroups,
            ] = await Promise.all([
                enumsApi.getAttendanceStatuses(),
                enumsApi.getLeaveRequestStatuses(),
                enumsApi.getLeaveTypes(),
                enumsApi.getEmployeeTypes(),
                enumsApi.getPermissions(),
                enumsApi.getPermissionGroups(),
            ]);

            return {
                attendanceStatuses,
                leaveRequestStatuses,
                leaveTypes,
                employeeTypes,
                permissions,
                permissionGroups,
            };
        } catch (error) {
            console.error("Failed to fetch all enums:", error);
            throw new Error("Unable to fetch all enums");
        }
    },
};