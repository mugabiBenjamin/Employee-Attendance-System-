import { api } from './index';
import type { EmergencyContact, PaginatedResponse } from './types';

export interface EmergencyQuery {
  id?: number;
  user_id?: number;
  page?: number;
  limit?: number;
  search?: string;
}

interface EmergencyContactData {
  name: string;
  relationship: string;
  phone: string;
  email?: string;
  address?: string;
  is_primary?: boolean;
}

export const emergencyApi = {
  getEmergencyContacts: async (query: EmergencyQuery): Promise<PaginatedResponse<EmergencyContact>> => {
    const response = await api.get<PaginatedResponse<EmergencyContact>>('/emergency-contacts', { params: query });
    return response.data;
  },

  createEmergencyContact: async (data: EmergencyContactData): Promise<EmergencyContact> => {
    const response = await api.post<EmergencyContact>('/emergency-contacts', data);
    return response.data;
  },

  updateEmergencyContact: async (id: number, data: EmergencyContactData): Promise<EmergencyContact> => {
    const response = await api.put<EmergencyContact>(`/emergency-contacts/${id}`, data);
    return response.data;
  },

  deleteEmergencyContact: async (id: number): Promise<void> => {
    await api.delete(`/emergency-contacts/${id}`);
  },
};