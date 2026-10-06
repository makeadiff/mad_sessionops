import axios, {
  AxiosInstance,
  AxiosError,
  AxiosRequestConfig,
  InternalAxiosRequestConfig,
  AxiosResponse,
} from "axios";
import { getAccessToken, getRefreshToken, storeDispatch } from "@/lib/redux/storeAccessor";
import { setAuthCookie, clearAuthCookie } from "@/lib/auth/cookieUtils";

// ============================================================================
// CONFIGURATION
// ============================================================================

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const REQUEST_TIMEOUT = parseInt(process.env.NEXT_PUBLIC_API_TIMEOUT || "30000", 10);

// Prevent multiple simultaneous refresh calls — queue waiting requests.
let isRefreshing = false;
let refreshSubscribers: ((token: string) => void)[] = [];
let refreshFailedSubscribers: (() => void)[] = [];

function subscribeTokenRefresh(cb: (token: string) => void) {
  refreshSubscribers.push(cb);
}

function subscribeTokenRefreshFailed(cb: () => void) {
  refreshFailedSubscribers.push(cb);
}

function onTokenRefreshed(token: string) {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
  refreshFailedSubscribers = [];
}

function onTokenRefreshFailed() {
  refreshFailedSubscribers.forEach((cb) => cb());
  refreshSubscribers = [];
  refreshFailedSubscribers = [];
}

// ============================================================================
// AXIOS INSTANCE
// ============================================================================

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: REQUEST_TIMEOUT,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
  responseType: "json",
  withCredentials: true,
});

// ============================================================================
// REQUEST INTERCEPTOR
// ============================================================================

/** Request config plus the fields the interceptors attach. */
type TrackedConfig = InternalAxiosRequestConfig & {
  metadata?: { startTime: number };
  _retry?: boolean;
};

/** Error bodies the backend may return (Ninja `detail`, or our envelopes). */
type ErrorBody = {
  detail?: string;
  message?: string;
  code?: string;
  errors?: unknown;
  error?: { message?: string };
};

apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Read token from Redux store (single source of truth).
    const token = getAccessToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    if (config.headers) {
      config.headers["X-Request-ID"] = generateRequestId();
      config.headers["X-Client-Version"] = "1.0.0";
      config.headers["X-Client-Platform"] = "web";
      config.headers["X-Timezone"] = Intl.DateTimeFormat().resolvedOptions().timeZone;
      config.headers["Accept-Language"] = navigator.language;
    }

    (config as TrackedConfig).metadata = { startTime: Date.now() };

    if (process.env.NODE_ENV === "development") {
      console.group(`🚀 API Request: ${config.method?.toUpperCase()} ${config.url}`);
      console.log("URL:", `${config.baseURL}${config.url}`);
      console.log("Data:", config.data);
      console.groupEnd();
    }

    return config;
  },
  (error: AxiosError) => {
    console.error("❌ Request setup failed:", error);
    return Promise.reject({
      message: "Failed to setup request",
      code: "REQUEST_SETUP_ERROR",
      originalError: error,
    });
  }
);

// ============================================================================
// RESPONSE INTERCEPTOR
// ============================================================================

apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    const config = response.config as TrackedConfig;
    if (config.metadata?.startTime) {
      const duration = Date.now() - config.metadata.startTime;
      if (duration > 3000) console.warn(`⚠️ Slow API request (${duration}ms):`, config.url);
      if (process.env.NODE_ENV === "development") {
        console.group(`✅ API Response: ${config.method?.toUpperCase()} ${config.url}`);
        console.log("Status:", response.status, "Duration:", `${duration}ms`);
        console.groupEnd();
      }
    }
    return response;
  },

  async (error: AxiosError) => {
    const config = error.config as TrackedConfig;
    const response = error.response;

    if (process.env.NODE_ENV === "development" && config?.metadata?.startTime) {
      const duration = Date.now() - config.metadata.startTime;
      console.group(`❌ API Error: ${config.method?.toUpperCase()} ${config.url}`);
      console.log("Status:", response?.status, "Duration:", `${duration}ms`);
      console.groupEnd();
    }

    // 1. Network error
    if (!response) {
      return Promise.reject({
        message: "Network error. Please check your internet connection.",
        code: "NETWORK_ERROR",
        status: 0,
      });
    }

    // 2. 401 — either a business-level auth failure or an expired session
    if (response.status === 401) {
      const url = config?.url || "";
      const isRefreshEndpoint = url.includes("/auth/refresh");

      // These public endpoints legitimately return 401 as a business error
      // (wrong password, invalid token, etc.). Do NOT attempt a token refresh —
      // just surface the error message so the form can display it.
      const isPublicAuthEndpoint =
        url.includes("/auth/login") ||
        url.includes("/auth/register") ||
        url.includes("/auth/google") ||
        url.includes("/auth/password/reset") ||
        url.includes("/auth/password/forgot") ||
        url.includes("/auth/password/validate");

      if (isRefreshEndpoint) {
        // Refresh token itself is expired — log out.
        clearAuthCookie();
        storeDispatch({ type: "auth/resetAuth" });
        if (typeof window !== "undefined") window.location.href = "/login";
        return Promise.reject({
          message: "Session expired. Please sign in again.",
          code: "SESSION_EXPIRED",
          status: 401,
        });
      }

      if (isPublicAuthEndpoint) {
        // Pass the backend message straight through — no redirect, no refresh.
        const errorData = response.data as ErrorBody | undefined;
        return Promise.reject({
          message: extractMessage(errorData) || "Authentication failed.",
          code: "AUTH_ERROR",
          status: 401,
          data: errorData,
        });
      }

      // Already retried once after a token refresh — don't loop.
      if (config._retry) {
        clearAuthCookie();
        storeDispatch({ type: "auth/resetAuth" });
        if (typeof window !== "undefined") window.location.href = "/login";
        return Promise.reject({
          message: "Session expired. Please sign in again.",
          code: "SESSION_EXPIRED",
          status: 401,
        });
      }

      // Protected endpoint returned 401 — access token expired, try refresh.
      if (!isRefreshing) {
        isRefreshing = true;

        try {
          const refreshToken = getRefreshToken();
          if (!refreshToken) throw new Error("No refresh token available");

          const refreshResponse = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          });

          const { accessToken, refreshToken: newRefreshToken } = refreshResponse.data;

          storeDispatch({
            type: "auth/updateTokens",
            payload: { accessToken, refreshToken: newRefreshToken },
          });
          setAuthCookie(accessToken);

          onTokenRefreshed(accessToken);

          if (config.headers) {
            config.headers.Authorization = `Bearer ${accessToken}`;
          }

          isRefreshing = false;
          config._retry = true;
          return apiClient.request(config);
        } catch {
          isRefreshing = false;
          onTokenRefreshFailed();
          clearAuthCookie();
          storeDispatch({ type: "auth/resetAuth" });
          if (typeof window !== "undefined") window.location.href = "/login";
          return Promise.reject({
            message: "Session expired. Please sign in again.",
            code: "SESSION_EXPIRED",
            status: 401,
          });
        }
      }

      return new Promise((resolve, reject) => {
        subscribeTokenRefresh((token: string) => {
          if (config.headers) {
            config.headers.Authorization = `Bearer ${token}`;
          }
          config._retry = true;
          resolve(apiClient.request(config));
        });
        subscribeTokenRefreshFailed(() => {
          reject({
            message: "Session expired. Please sign in again.",
            code: "SESSION_EXPIRED",
            status: 401,
          });
        });
      });
    }

    // 3–8. Other HTTP errors
    if (response.status === 403) {
      return Promise.reject({
        message: "You do not have permission to perform this action.",
        code: "FORBIDDEN",
        status: 403,
        data: response.data,
      });
    }

    if (response.status === 404) {
      const errorData = response.data as ErrorBody | undefined;
      return Promise.reject({
        message: extractMessage(errorData) || "The requested resource was not found.",
        code: "NOT_FOUND",
        status: 404,
        data: errorData,
      });
    }

    if (response.status === 422) {
      const errorData = response.data as ErrorBody | undefined;
      return Promise.reject({
        message: extractMessage(errorData) || "Validation error",
        code: "VALIDATION_ERROR",
        status: 422,
        errors: errorData?.errors,
        data: errorData,
      });
    }

    if (response.status === 429) {
      const retryAfter = response.headers["retry-after"];
      return Promise.reject({
        message: `Too many requests. Please try again ${retryAfter ? `after ${retryAfter} seconds` : "later"}.`,
        code: "RATE_LIMIT_EXCEEDED",
        status: 429,
        retryAfter,
      });
    }

    if (response.status >= 500) {
      return Promise.reject({
        message: "Server error. Please try again later.",
        code: "SERVER_ERROR",
        status: response.status,
        data: response.data,
      });
    }

    const errorData = response.data as ErrorBody | undefined;
    return Promise.reject({
      message: extractMessage(errorData) || "An unexpected error occurred",
      code: errorData?.code || "UNKNOWN_ERROR",
      status: response.status,
      errors: errorData?.errors,
      data: errorData,
    });
  }
);

// ============================================================================
// HELPERS
// ============================================================================

function generateRequestId(): string {
  return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Extract a human-readable message from a backend error body.
 * Django Ninja's HttpError returns { detail: "..." }.
 * Custom error envelopes may use { message: "..." } or { error: { message: "..." } }.
 */
function extractMessage(data: ErrorBody | undefined): string | undefined {
  if (!data) return undefined;
  return data.detail ?? data.message ?? data.error?.message ?? undefined;
}

// ============================================================================
// API CLIENT METHODS
// ============================================================================

export async function get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return (await apiClient.get<T>(url, config)).data;
}

export async function post<T = unknown>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> {
  return (await apiClient.post<T>(url, data, config)).data;
}

export async function put<T = unknown>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> {
  return (await apiClient.put<T>(url, data, config)).data;
}

export async function patch<T = unknown>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> {
  return (await apiClient.patch<T>(url, data, config)).data;
}

export async function del<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return (await apiClient.delete<T>(url, config)).data;
}

export async function upload<T = unknown>(
  url: string,
  file: File,
  onProgress?: (progress: number) => void
): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);

  return (
    await apiClient.post<T>(url, formData, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => {
        if (e.total && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
      },
    })
  ).data;
}

/** Shape the response interceptor rejects with. */
export interface ApiRejection {
  message: string;
  code: string;
  status?: number;
  data?: unknown;
}

/**
 * Read `filename="..."` from a Content-Disposition header (backend must expose
 * it via CORS_EXPOSE_HEADERS for cross-origin requests).
 */
export function filenameFromDisposition(header: string | undefined): string | undefined {
  if (!header) return undefined;
  const match = /filename="?([^";]+)"?/i.exec(header);
  return match?.[1];
}

/**
 * GET a file and save it via a temporary link. Errors keep the interceptor's
 * shape; for blob responses the JSON error body is parsed so `message`
 * carries the backend's text.
 */
export async function download(
  url: string,
  fallbackFilename: string,
  params?: Record<string, unknown>
): Promise<void> {
  let response: AxiosResponse<Blob>;
  try {
    response = await apiClient.get<Blob>(url, {
      params,
      responseType: "blob",
      headers: { Accept: "text/csv, application/json" },
    });
  } catch (caught) {
    const error = caught as ApiRejection;
    // 403 and 5xx keep the interceptor's generic message, same as JSON requests.
    const status = error?.status ?? 0;
    if (error?.data instanceof Blob && status !== 403 && status < 500) {
      try {
        const body = JSON.parse(await error.data.text());
        error.message = extractMessage(body) || error.message;
        error.data = body;
      } catch {
        // Non-JSON error body — keep the interceptor's message.
      }
    }
    throw error;
  }

  const filename =
    filenameFromDisposition(response.headers?.["content-disposition"]) || fallbackFilename;
  const blob = new Blob([response.data], {
    type: response.headers?.["content-type"] || "text/csv;charset=utf-8",
  });
  const href = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoke after the click has been handled, or some browsers cancel the download.
  setTimeout(() => window.URL.revokeObjectURL(href), 0);
}

export const api = { get, post, put, patch, delete: del, upload, download };

export default apiClient;
