import { useState, useCallback } from 'react';
import { AxiosError, type AxiosResponse } from 'axios';

// Define interface for the hook's return type
interface ApiResponse<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  execute: (...args: unknown[]) => Promise<void>;
}

// Generic hook for API calls
export function useApi<T>(apiCall: (...args: unknown[]) => Promise<AxiosResponse<T>>): ApiResponse<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const execute = useCallback(async (...args: unknown[]): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiCall(...args);
      setData(response.data);
    } catch (err) {
      const axiosError = err as AxiosError<{ message?: string }>;
      setError(axiosError.response?.data?.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [apiCall]);

  return { data, error, loading, execute };
}