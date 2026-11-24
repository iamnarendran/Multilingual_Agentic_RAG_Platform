export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const TOKEN_KEY = "akshara.token";

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private mode): the session lasts until reload */
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

type Unauthorized = () => void;
let onUnauthorized: Unauthorized = () => {};
export function setUnauthorizedHandler(handler: Unauthorized) {
  onUnauthorized = handler;
}

function describe(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    // FastAPI validation errors: [{loc, msg}, ...]
    const first = detail[0] as { loc?: unknown[]; msg?: string };
    const field = first.loc?.[first.loc.length - 1];
    if (field === "password") return "Use a password of at least 8 characters.";
    if (field === "email") return "Enter a valid email address.";
    return first.msg || "Some fields are invalid.";
  }
  if (status >= 500) return "The server hit an error. Try again in a moment.";
  return `Request failed (${status}).`;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const token = getToken();
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...rest,
      headers: {
        ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(`Can't reach the server at ${API_URL}. Check that the backend is running.`, 0);
  }
  if (response.status === 401 && token) onUnauthorized();
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = (await response.json()).detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(describe(detail, response.status), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const fetcher = <T,>(path: string) => api<T>(path);
