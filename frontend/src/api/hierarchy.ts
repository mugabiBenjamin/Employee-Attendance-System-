import { api } from './index';
import type { EmployeeHierarchy } from './types';

interface HierarchyData {
  employee_id: number;
  manager_id: number;
}

export const hierarchyApi = {
  getHierarchy: async (): Promise<EmployeeHierarchy[]> => {
    const response = await api.get<EmployeeHierarchy[]>('/employee-hierarchy');
    return response.data;
  },

  assignManager: async (data: HierarchyData): Promise<EmployeeHierarchy> => {
    const response = await api.post<EmployeeHierarchy>('/employee-hierarchy', data);
    return response.data;
  },

  removeManager: async (employee_id: number): Promise<void> => {
    await api.delete(`/employee-hierarchy/${employee_id}`);
  },
};