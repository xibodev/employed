import { getApiUrl } from "@/lib/runtime-config";
import type { ApiErrorShape, Job, JobFormValues, JobsQuery, PaginatedResponse } from "@/lib/types";

function getApiBaseUrl(): string {
  // EMP-012 (Rule 11): resolved at call time from runtime config, so an
  // API-URL change is a restart, not a rebuild.
  const apiBaseUrl = getApiUrl();
  if (typeof window !== "undefined") {
    return apiBaseUrl;
  }

  return apiBaseUrl.replace("http://localhost:3301", "http://backend:8000")
    .replace("http://127.0.0.1:3301", "http://backend:8000")
    .replace("http://localhost:8000", "http://backend:8000")
    .replace("http://127.0.0.1:8000", "http://backend:8000");
}

export class ApiError extends Error {
  status: number;
  payload?: ApiErrorShape | string;

  constructor(message: string, status: number, payload?: ApiErrorShape | string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  host?: string;
  token?: string;
  query?: Record<string, string | number | boolean | undefined | null>;
  body?: BodyInit | Record<string, unknown> | null;
}

function getClientToken(): string | undefined {
  if (typeof window === "undefined") return undefined;
  return window.localStorage.getItem("employed_token") ?? undefined;
}

function getClientHost(): string | undefined {
  if (typeof window === "undefined") return undefined;
  return window.location.host;
}

function buildUrl(path: string, query?: ApiFetchOptions["query"]): string {
  const url = new URL(path, getApiBaseUrl());
  if (query) {
    Object.entries(query).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      url.searchParams.set(key, String(value));
    });
  }
  return url.toString();
}

function normaliseBody(body: ApiFetchOptions["body"], headers: Headers): BodyInit | undefined {
  if (body == null) return undefined;
  if (typeof body === "string" || body instanceof FormData || body instanceof URLSearchParams || body instanceof Blob) {
    return body;
  }
  headers.set("Content-Type", "application/json");
  return JSON.stringify(body);
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { host, token, query, body, headers, ...init } = options;
  const requestHeaders = new Headers(headers);
  requestHeaders.set("Accept", "application/json");

  const resolvedHost = host ?? getClientHost();
  if (resolvedHost) {
    requestHeaders.set("X-Forwarded-Host", resolvedHost);
  }

  const resolvedToken = token ?? getClientToken();
  if (resolvedToken) {
    requestHeaders.set("Authorization", `Bearer ${resolvedToken}`);
  }

  const response = await fetch(buildUrl(path, query), {
    ...init,
    headers: requestHeaders,
    body: normaliseBody(body, requestHeaders)
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === "string"
        ? payload
        : typeof payload?.detail === "string"
          ? payload.detail
          : payload?.message ?? `Request failed with status ${response.status}`;

    throw new ApiError(message, response.status, payload);
  }

  return payload as T;
}

export async function getJobs(query: JobsQuery, options: Omit<ApiFetchOptions, "query"> = {}) {
  if (query.featured) {
    const items = await apiFetch<Job[]>("/api/featuredJobs", {
      ...options,
      cache: options.cache ?? "no-store"
    });
    return {
      items,
      total: items.length,
      page: 1,
      per_page: items.length,
      total_pages: 1
    } as PaginatedResponse<Job>;
  }

  const payload = await apiFetch<{ items: Job[]; total: number; page: number; page_size: number }>("/api/jobs", {
    ...options,
    query: {
      query: query.search,
      jobtype: query.job_type,
      remote: query.remote,
      page: query.page,
      page_size: query.per_page
    },
    cache: options.cache ?? "no-store"
  });

  return {
    items: payload.items,
    total: payload.total,
    page: payload.page,
    per_page: payload.page_size,
    total_pages: Math.max(1, Math.ceil(payload.total / Math.max(payload.page_size, 1)))
  } satisfies PaginatedResponse<Job>;
}

export async function getJob(id: string, options: Omit<ApiFetchOptions, "query"> = {}) {
  return apiFetch<Job>(`/jobs/${id}`, {
    ...options,
    cache: options.cache ?? "no-store"
  });
}

export async function createJob(payload: JobFormValues, options: Omit<ApiFetchOptions, "body"> = {}) {
  return apiFetch<Job>("/jobs", {
    ...options,
    method: "POST",
    body: payload as unknown as Record<string, unknown>
  });
}

export async function updateJob(id: string, payload: Partial<JobFormValues> & { status?: string }, options: Omit<ApiFetchOptions, "body"> = {}) {
  return apiFetch<Job>(`/jobs/${id}`, {
    ...options,
    method: "PUT",
    body: payload as unknown as Record<string, unknown>
  });
}

export async function deleteJob(id: string, options: Omit<ApiFetchOptions, "body"> = {}) {
  return apiFetch<void>(`/jobs/${id}`, {
    ...options,
    method: "DELETE"
  });
}
