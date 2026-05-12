/**
 * API Client — Fetch wrapper with JWT auth.
 * All API calls go through this module.
 */

// Default to empty so all calls are SAME-ORIGIN. Next.js rewrites in
// next.config.ts proxy /api/* server-side to INTERNAL_API_URL. This avoids
// CORS, mixed-content, and Chrome's Private Network Access prompt that fires
// when a public-origin page tries to fetch from a private/loopback address.
// Override only for dev when running `next dev` against a separate API server
// (e.g. NEXT_PUBLIC_API_URL=http://localhost:5055).
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
const REQUEST_TIMEOUT_MS = 30_000;

type RequestOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  timeoutMs?: number;
};

class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("cmd_support_token");
}

export function setToken(token: string) {
  localStorage.setItem("cmd_support_token", token);
}

export function clearToken() {
  localStorage.removeItem("cmd_support_token");
}

export async function api<T = unknown>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, headers = {}, timeoutMs = REQUEST_TIMEOUT_MS } = options;
  const token = getToken();

  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeoutMs);

  const config: RequestInit = {
    method,
    signal: controller.signal,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  };

  if (body && method !== "GET") {
    config.body = JSON.stringify(body);
  }

  let res: Response;
  const fullUrl = `${API_BASE}${path}`;
  console.log(`[API] Fetching: ${method} ${fullUrl}`);
  try {
    res = await fetch(fullUrl, config);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        0,
        `Yêu cầu vượt quá ${Math.round(timeoutMs / 1000)}s. Máy chủ AI có thể đang quá tải — vui lòng thử lại.`,
      );
    }
    throw err;
  } finally {
    clearTimeout(timerId);
  }

  if (!res.ok) {
    let data;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    const message =
      (data as { detail?: string })?.detail || `API Error ${res.status}`;
    throw new ApiError(res.status, message, data);
  }

  // Handle empty responses (204, etc.)
  const text = await res.text();
  if (!text) return {} as T;
  return JSON.parse(text);
}

/**
 * Upload a file via multipart/form-data.
 */
export async function apiUpload<T = unknown>(
  path: string,
  formData: FormData,
  timeoutMs = 120_000
): Promise<T> {
  const token = getToken();
  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      signal: controller.signal,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "Upload timed out");
    }
    throw err;
  } finally {
    clearTimeout(timerId);
  }

  if (!res.ok) {
    let data;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    const message =
      (data as { detail?: string })?.detail || `Upload Error ${res.status}`;
    throw new ApiError(res.status, message, data);
  }

  return res.json();
}

export { ApiError };
