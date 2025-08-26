import axios, { type AxiosInstance } from 'axios';
import { authApi } from './auth';
import { attendanceApi } from './attendance';
import { departmentsApi } from './departments';
import { emergencyApi } from './emergency';
import { hierarchyApi } from './hierarchy';
import { shiftsApi } from './shifts';
import { logsApi } from './logs';
import { usersApi } from './users';
import { holidaysApi } from './holidays';
import { leaveApi } from './leave';
import { overtimeApi } from './overtime';
import { rolesApi } from './roles';

const api: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add interceptor to include JWT token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export { api, authApi, attendanceApi, departmentsApi, emergencyApi, hierarchyApi, shiftsApi, logsApi, usersApi, holidaysApi, leaveApi, overtimeApi, rolesApi };