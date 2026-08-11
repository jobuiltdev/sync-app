import { api } from '@/api/client';

export interface HealthResponse {
  status: 'ok' | 'degraded';
  checks: {
    database: 'ok' | 'error';
    cache: 'ok' | 'error';
  };
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return api.get<HealthResponse>('/api/v1/health/', { signal });
}

export const healthKeys = {
  root: ['health'] as const,
};
