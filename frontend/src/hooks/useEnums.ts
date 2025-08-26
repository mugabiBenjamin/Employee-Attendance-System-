import { useQuery } from '@tanstack/react-query';
import { enumsApi } from '../api/enums';
import { enumsCache } from '../lib/enumsCache';
import type {
    AttendanceStatus,
    LeaveRequestStatus,
    LeaveType,
    EmployeeType,
    EnumOption
} from '../api/types';

// Query keys
const ENUM_KEYS = {
    attendanceStatuses: ['enums', 'attendanceStatuses'] as const,
    leaveRequestStatuses: ['enums', 'leaveRequestStatuses'] as const,
    leaveTypes: ['enums', 'leaveTypes'] as const,
    employeeTypes: ['enums', 'employeeTypes'] as const,
    permissions: ['enums', 'permissions'] as const,
    permissionGroups: ['enums', 'permissionGroups'] as const,
    all: ['enums', 'all'] as const,
};

// Individual enum hooks
export const useAttendanceStatuses = () => {
    return useQuery({
        queryKey: ENUM_KEYS.attendanceStatuses,
        queryFn: enumsApi.getAttendanceStatuses,
        initialData: () => enumsCache.get('attendanceStatuses'),
        staleTime: 1000 * 60 * 60, // 1 hour
        gcTime: 1000 * 60 * 60 * 24, // 24 hours
    });
};

export const useLeaveRequestStatuses = () => {
    return useQuery({
        queryKey: ENUM_KEYS.leaveRequestStatuses,
        queryFn: enumsApi.getLeaveRequestStatuses,
        initialData: () => enumsCache.get('leaveRequestStatuses'),
        staleTime: 1000 * 60 * 60,
        gcTime: 1000 * 60 * 60 * 24,
    });
};

export const useLeaveTypes = () => {
    return useQuery({
        queryKey: ENUM_KEYS.leaveTypes,
        queryFn: enumsApi.getLeaveTypes,
        initialData: () => enumsCache.get('leaveTypes'),
        staleTime: 1000 * 60 * 60,
        gcTime: 1000 * 60 * 60 * 24,
    });
};

export const useEmployeeTypes = () => {
    return useQuery({
        queryKey: ENUM_KEYS.employeeTypes,
        queryFn: enumsApi.getEmployeeTypes,
        initialData: () => enumsCache.get('employeeTypes'),
        staleTime: 1000 * 60 * 60,
        gcTime: 1000 * 60 * 60 * 24,
    });
};

export const usePermissions = () => {
    return useQuery({
        queryKey: ENUM_KEYS.permissions,
        queryFn: enumsApi.getPermissions,
        initialData: () => enumsCache.get('permissions'),
        staleTime: 1000 * 60 * 60,
        gcTime: 1000 * 60 * 60 * 24,
    });
};

export const usePermissionGroups = () => {
    return useQuery({
        queryKey: ENUM_KEYS.permissionGroups,
        queryFn: enumsApi.getPermissionGroups,
        initialData: () => enumsCache.get('permissionGroups'),
        staleTime: 1000 * 60 * 60,
        gcTime: 1000 * 60 * 60 * 24,
    });
};

// Combined hook for all enums
export const useAllEnums = () => {
    return useQuery({
        queryKey: ENUM_KEYS.all,
        queryFn: enumsApi.getAllEnums,
        staleTime: 1000 * 60 * 60,
        gcTime: 1000 * 60 * 60 * 24,
    });
};

// Utility hooks for formatted options
export const useAttendanceStatusOptions = (): EnumOption<AttendanceStatus>[] => {
    const { data = [] } = useAttendanceStatuses();
    return data.map(status => ({
        value: status,
        label: status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
    }));
};

export const useLeaveTypeOptions = (): EnumOption<LeaveType>[] => {
    const { data = [] } = useLeaveTypes();
    return data.map(type => ({
        value: type,
        label: type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
    }));
};

export const useEmployeeTypeOptions = (): EnumOption<EmployeeType>[] => {
    const { data = [] } = useEmployeeTypes();
    return data.map(type => ({
        value: type,
        label: type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
    }));
};

export const useLeaveRequestStatusOptions = (): EnumOption<LeaveRequestStatus>[] => {
    const { data = [] } = useLeaveRequestStatuses();
    return data.map(status => ({
        value: status,
        label: status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
    }));
};

// Permission helper hooks
export const useUserPermissions = (userRole?: string) => {
    const { data: permissionGroups } = usePermissionGroups();

    if (!userRole || !permissionGroups) return [];

    return permissionGroups[userRole] || [];
};

export const useHasPermission = (permission: string, userRole?: string): boolean => {
    const userPermissions = useUserPermissions(userRole);
    return userPermissions.includes(permission) || userPermissions.includes('all_permissions');
};