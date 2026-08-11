import { QueryClient } from '@tanstack/react-query';

import { ApiError } from '@/api/errors';

/**
 * Retry policy is tuned for Nigerian mobile networks, where a failed request is
 * far more often a dropped connection than a real server error. Connectivity
 * failures are retried; anything the server answered deliberately is not, since
 * repeating a 400 or a 403 only wastes the user's data.
 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 3) return false;
  if (error instanceof ApiError) {
    return error.isConnectivityError || (error.status !== null && error.status >= 500);
  }
  return false;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
      mutations: {
        // Mutations are only safe to retry when they carry an idempotency key,
        // so the decision belongs to each call site rather than here.
        retry: false,
      },
    },
  });
}
