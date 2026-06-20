import { getApiUrl } from "@/lib/runtime-config";
import type { CompanyMembership } from "@/lib/tenant";
import type {
  ApiErrorShape,
  Company,
  CompanyCreateValues,
  DomainVerifyValues,
  Job,
  JobFormValues,
  JobsQuery,
  Membership,
  MembershipInviteValues,
  PaginatedResponse,
} from "@/lib/types";

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

// --- Companies (multi-tenant hiring platform) ---

/**
 * Create a Company (`POST /companies`). The owning market is resolved
 * server-side from the request hostname; the authenticated user becomes the
 * active `org_owner`.
 */
export async function createCompany(payload: CompanyCreateValues, options: Omit<ApiFetchOptions, "body"> = {}) {
  return apiFetch<Company>("/companies", {
    ...options,
    method: "POST",
    body: payload as unknown as Record<string, unknown>,
    cache: options.cache ?? "no-store"
  });
}

/** Read a single Company by id (`GET /companies/{id}`). */
export async function getCompany(companyId: string, options: Omit<ApiFetchOptions, "query"> = {}) {
  return apiFetch<Company>(`/companies/${companyId}`, {
    ...options,
    cache: options.cache ?? "no-store"
  });
}

/**
 * Verify a Company domain (`POST /companies/{id}/verify-domain`) via DNS TXT or
 * matching member emails. Returns the updated Company on success.
 */
export async function verifyCompanyDomain(
  companyId: string,
  payload: DomainVerifyValues,
  options: Omit<ApiFetchOptions, "body"> = {}
) {
  return apiFetch<Company>(`/companies/${companyId}/verify-domain`, {
    ...options,
    method: "POST",
    body: payload as unknown as Record<string, unknown>,
    cache: options.cache ?? "no-store"
  });
}

// --- Memberships ---

/**
 * List the companies the authenticated user belongs to
 * (`GET /users/me/memberships`). Server-fed source for the tenant switcher;
 * each row is already shaped as a {@link CompanyMembership}.
 */
export async function listMyMemberships(options: Omit<ApiFetchOptions, "query"> = {}) {
  return apiFetch<CompanyMembership[]>("/users/me/memberships", {
    ...options,
    cache: options.cache ?? "no-store"
  });
}

/** List a Company's memberships (`GET /companies/{companyId}/members`). */
export async function listMembers(companyId: string, options: Omit<ApiFetchOptions, "query"> = {}) {
  return apiFetch<Membership[]>(`/companies/${companyId}/members`, {
    ...options,
    cache: options.cache ?? "no-store"
  });
}

/** Invite a user to a Company (`POST /companies/{companyId}/members`). */
export async function inviteMember(
  companyId: string,
  payload: MembershipInviteValues,
  options: Omit<ApiFetchOptions, "body"> = {}
) {
  return apiFetch<Membership>(`/companies/${companyId}/members`, {
    ...options,
    method: "POST",
    body: payload as unknown as Record<string, unknown>,
    cache: options.cache ?? "no-store"
  });
}

/** Accept an invitation (`POST /companies/{companyId}/members/{membershipId}/accept`). */
export async function acceptMembership(
  companyId: string,
  membershipId: string,
  options: Omit<ApiFetchOptions, "body"> = {}
) {
  return apiFetch<Membership>(`/companies/${companyId}/members/${membershipId}/accept`, {
    ...options,
    method: "POST",
    cache: options.cache ?? "no-store"
  });
}

/** Suspend a membership (`POST /companies/{companyId}/members/{membershipId}/suspend`). */
export async function suspendMembership(
  companyId: string,
  membershipId: string,
  options: Omit<ApiFetchOptions, "body"> = {}
) {
  return apiFetch<Membership>(`/companies/${companyId}/members/${membershipId}/suspend`, {
    ...options,
    method: "POST",
    cache: options.cache ?? "no-store"
  });
}

// ---------------------------------------------------------------------------
// Applications & recruiter pipeline (R17) — added by task 18.3.
// Self-contained section to avoid collisions with parallel edits to this file.
// ---------------------------------------------------------------------------

/** Fixed pipeline stages (mirrors backend `ApplicationStatus`, R16.3). */
export type ApplicationStatus = "applied" | "reviewed" | "shortlisted" | "rejected" | "hired";

/** A tracked application as returned by the recruiter endpoints (R16/R17). */
export interface Application {
  id: string;
  job_id: string;
  company_id: string | null;
  candidate_user_id: string | null;
  candidate_snapshot: Record<string, unknown> | null;
  status: ApplicationStatus;
  resume_version_id: string | null;
  cover_note: string | null;
  source: string;
}

/**
 * List the applications for a company (R17.1).
 * GET /companies/{company_id}/applications — permission-guarded server-side.
 */
export async function listApplications(companyId: string, options: Omit<ApiFetchOptions, "query"> = {}) {
  return apiFetch<Application[]>(`/companies/${companyId}/applications`, {
    ...options,
    cache: options.cache ?? "no-store",
  });
}

/**
 * Advance an application to a new pipeline stage (R17.3).
 * PATCH /applications/{application_id}/status — returns the updated application.
 */
export async function changeApplicationStatus(
  applicationId: string,
  newStatus: ApplicationStatus,
  options: Omit<ApiFetchOptions, "body"> = {},
) {
  return apiFetch<Application>(`/applications/${applicationId}/status`, {
    ...options,
    method: "PATCH",
    body: { new_status: newStatus },
    cache: options.cache ?? "no-store",
  });
}
