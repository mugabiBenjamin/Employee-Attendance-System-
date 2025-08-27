import { api } from './index';
import type { PaginatedResponse, LeaveRequest, LeaveBalance, LeavePolicy, LeaveApproval, LeaveRequestStatus, LeaveType } from './types';

interface LeaveRequestQuery {
    user_id?: number;
    start_date?: string;
    end_date?: string;
    status?: LeaveRequestStatus;
    page?: number;
    limit?: number;
}

interface LeaveRequestData {
    user_id: number;
    start_date: string;
    end_date: string;
    leave_type: LeaveType;
    reason?: string;
}

interface LeaveApprovalData {
    leave_request_id: number;
    status: LeaveRequestStatus;
    comments?: string;
}

interface LeaveBalanceQuery {
    user_id?: number;
    leave_type?: LeaveType;
    page?: number;
    limit?: number;
}

interface LeavePolicyQuery {
    page?: number;
    limit?: number;
}

interface LeavePolicyData {
    name: string;
    description?: string;
    leave_type: LeaveType;
    max_days: number;
}

export const leaveApi = {
    getLeaveRequests: async (query: LeaveRequestQuery): Promise<PaginatedResponse<LeaveRequest>> => {
        const response = await api.get<PaginatedResponse<LeaveRequest>>('/leave-requests', { params: query });
        return response.data;
    },

    createLeaveRequest: async (data: LeaveRequestData): Promise<LeaveRequest> => {
        const response = await api.post<LeaveRequest>('/leave-requests', data);
        return response.data;
    },

    approveLeave: async (data: LeaveApprovalData): Promise<LeaveApproval> => {
        const response = await api.post<LeaveApproval>('/leave-approval-workflow/approve', data);
        return response.data;
    },

    getLeaveBalances: async (query: LeaveBalanceQuery): Promise<PaginatedResponse<LeaveBalance>> => {
        const response = await api.get<PaginatedResponse<LeaveBalance>>('/leave-balances', { params: query });
        return response.data;
    },

    getLeavePolicies: async (query: LeavePolicyQuery): Promise<PaginatedResponse<LeavePolicy>> => {
        const response = await api.get<PaginatedResponse<LeavePolicy>>('/leave-policies', { params: query });
        return response.data;
    },

    createLeavePolicy: async (data: LeavePolicyData): Promise<LeavePolicy> => {
        const response = await api.post<LeavePolicy>('/leave-policies', data);
        return response.data;
    },

    updateLeavePolicy: async (id: number, data: LeavePolicyData): Promise<LeavePolicy> => {
        const response = await api.put<LeavePolicy>(`/leave-policies/${id}`, data);
        return response.data;
    },

    deleteLeavePolicy: async (id: number): Promise<void> => {
        await api.delete(`/leave-policies/${id}`);
    },
};