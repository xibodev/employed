import type { CompanyMembership } from "@/lib/tenant";

/**
 * Client-side store for the memberships that hydrate `TenantProvider`.
 *
 * The backend does not (yet) expose an aggregate "my memberships" endpoint, so
 * the active company set is assembled on the client from the companies a user
 * creates or loads during a session and persisted to `localStorage`. This keeps
 * the tenant axis decoupled from market (R1.6) and survives reloads, while the
 * provider itself stays a pure function of its `memberships` prop — a future
 * server-fed source can replace this store without touching the provider.
 */

/** localStorage key holding the serialized membership list. */
export const MEMBERSHIPS_STORAGE_KEY = "employed_memberships";

/** Window event dispatched whenever the stored membership set changes. */
export const MEMBERSHIPS_CHANGED_EVENT = "employed:memberships-changed";

function isCompanyMembership(value: unknown): value is CompanyMembership {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.id === "string" &&
    typeof record.name === "string" &&
    typeof record.slug === "string" &&
    typeof record.role === "string" &&
    typeof record.status === "string"
  );
}

/** Read the persisted membership list (browser only; always a fresh array). */
export function getStoredMemberships(): CompanyMembership[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(MEMBERSHIPS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(isCompanyMembership);
  } catch {
    return [];
  }
}

function writeStoredMemberships(memberships: CompanyMembership[]): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(MEMBERSHIPS_STORAGE_KEY, JSON.stringify(memberships));
  window.dispatchEvent(new Event(MEMBERSHIPS_CHANGED_EVENT));
}

/** Insert or update a membership by company id, then notify listeners. */
export function upsertStoredMembership(membership: CompanyMembership): CompanyMembership[] {
  const existing = getStoredMemberships().filter((item) => item.id !== membership.id);
  const next = [...existing, membership];
  writeStoredMemberships(next);
  return next;
}

/** Remove a membership by company id, then notify listeners. */
export function removeStoredMembership(companyId: string): CompanyMembership[] {
  const next = getStoredMemberships().filter((item) => item.id !== companyId);
  writeStoredMemberships(next);
  return next;
}

/**
 * Replace the entire stored membership set, then notify listeners.
 *
 * Used to reconcile the client store with the server-fed
 * ``GET /users/me/memberships`` response so the tenant switcher reflects the
 * authoritative set rather than only locally created/linked companies.
 */
export function replaceStoredMemberships(memberships: CompanyMembership[]): CompanyMembership[] {
  const next = memberships.filter(isCompanyMembership);
  writeStoredMemberships(next);
  return next;
}
