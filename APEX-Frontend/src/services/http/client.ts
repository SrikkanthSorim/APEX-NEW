import { API_BASE_URL } from "@/services/config/env";

export type ApiQueryValue = string | number | boolean | null | undefined;

export interface ApiRequestOptions extends Omit<RequestInit, "body" | "headers"> {
  baseUrl?: string;
  query?: Record<string, ApiQueryValue>;
  body?: BodyInit | object | null;
  headers?: HeadersInit;
}

/**
 * Build an Authorization header carrying a GitHub PAT, or an empty object when
 * no token is provided. Sending the token as a header (never in the URL query
 * string) keeps it out of browser history, server logs, proxies, and referrers.
 */
export function authHeader(token?: string | null): Record<string, string> {
  const trimmed = token?.trim();
  return trimmed ? { Authorization: `Bearer ${trimmed}` } : {};
}

export class ApiError extends Error {
  status: number;
  code?: string;
  detail?: unknown;

  constructor(message: string, status: number, code?: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

function getErrorMessage(detail: unknown, fallbackMessage = "Request failed"): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        if (item && typeof item === "object") {
          const typedItem = item as Record<string, unknown>;
          return typedItem.msg || typedItem.message || JSON.stringify(item);
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    const typedDetail = detail as Record<string, unknown>;
    return (
      (typeof typedDetail.message === "string" && typedDetail.message) ||
      (typeof typedDetail.msg === "string" && typedDetail.msg) ||
      fallbackMessage
    );
  }
  return fallbackMessage;
}

async function parseJsonResponse<T>(response: Response, fallbackMessage: string): Promise<T> {
  const contentType = response.headers.get("content-type") || "";
  const bodyText = await response.text();

  if (!contentType.includes("application/json")) {
    if (bodyText.trim().startsWith("<!doctype") || bodyText.trim().startsWith("<html")) {
      throw new Error(`API routing error: expected JSON from ${response.url} but received HTML. Check VITE_API_URL or backend routing.`);
    }
    throw new Error(fallbackMessage);
  }

  const data = JSON.parse(bodyText);
  if (!response.ok) {
    const detail = data?.detail;
    const errorMessage = typeof data?.error === "string" && data.error.trim()
      ? data.error
      : getErrorMessage(detail, fallbackMessage);
    const errorCode =
      detail && typeof detail === "object" && !Array.isArray(detail)
        ? (detail as Record<string, unknown>).code
        : undefined;
    throw new ApiError(
      errorMessage,
      response.status,
      typeof errorCode === "string" ? errorCode : undefined,
      detail,
    );
  }

  return data as T;
}

export async function readErrorDetail(response: Response): Promise<string | undefined> {
  const text = await response
    .clone()
    .text()
    .catch(() => "");

  if (!text) return undefined;

  try {
    const json = JSON.parse(text);
    if (typeof json === "string") return json;
    return getErrorMessage(json?.detail ?? json?.message ?? json?.error);
  } catch {
    return text;
  }
}

export const ABSOLUTE_URL_PATTERN = /^https?:\/\//i;

export function buildApiUrl(
  path: string,
  query: Record<string, ApiQueryValue> = {},
  baseUrl: string = API_BASE_URL
): string {
  const normalizedBaseUrl = baseUrl.replace(/\/+$/, "");
  const normalizedPath = path.replace(/^\/+/, "");
  const url = ABSOLUTE_URL_PATTERN.test(path)
    ? new URL(path)
    : new URL(normalizedPath, `${normalizedBaseUrl}/`);

  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return;
    }
    url.searchParams.set(key, String(value));
  });

  return url.toString();
}

function isBodyInitLike(body: NonNullable<ApiRequestOptions["body"]>): body is BodyInit {
  return (
    typeof body === "string" ||
    body instanceof Blob ||
    body instanceof FormData ||
    body instanceof URLSearchParams ||
    body instanceof ArrayBuffer ||
    ArrayBuffer.isView(body)
  );
}

function buildRequestInit(options: Omit<ApiRequestOptions, "baseUrl" | "query">): RequestInit {
  const { body, headers, ...init } = options;
  const requestHeaders = new Headers(headers);

  if (body == null) {
    return { ...init, headers: requestHeaders };
  }

  if (isBodyInitLike(body)) {
    return { ...init, headers: requestHeaders, body };
  }

  if (!requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }

  return {
    ...init,
    headers: requestHeaders,
    body: JSON.stringify(body),
  };
}

export async function performRequest(path: string, options: ApiRequestOptions = {}): Promise<Response> {
  const { baseUrl, query, ...requestInit } = options;
  return fetch(buildApiUrl(path, query, baseUrl), buildRequestInit(requestInit));
}

export async function requestJson<T>(
  path: string,
  fallbackMessage: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const response = await performRequest(path, options);
  return parseJsonResponse<T>(response, fallbackMessage);
}

export async function requestBlob(
  path: string,
  fallbackMessage: string,
  options: ApiRequestOptions = {}
): Promise<Blob> {
  const response = await performRequest(path, options);

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new ApiError(detail || fallbackMessage, response.status, undefined, detail);
  }

  return response.blob();
}
