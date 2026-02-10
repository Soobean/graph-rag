/**
 * Build URL search params string from a Record, omitting undefined/null values.
 */
export function buildSearchParams(params: Record<string, string | number | undefined>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      searchParams.set(key, String(value));
    }
  });
  return searchParams.toString();
}

/**
 * Extract a user-friendly error message from an Axios error response.
 */
export function getApiErrorMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string }; status?: number } }).response;
    if (response?.data?.detail) {
      return response.data.detail;
    }
    if (response?.status) {
      return `Server error (${response.status})`;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
}
