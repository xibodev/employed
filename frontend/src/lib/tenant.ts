import type { MarketKey } from "@/lib/types";

/**
 * Tenant (org/permission) axis — deliberately separate from `src/lib/market.ts`.
 *
 * `market.ts` resolves geography/locale/payment from the hostname. Tenant is an
 * orthogonal axis (R1.6): it describes the organization a user is acting on
 * behalf of and the permissions that flow from their membership. The active
 * company is selected from the user's memberships and is NEVER derived from the
 * hostname. The two axes never derive from each other.
 */

/** Tenant-scoped role carried by a Membership (mirrors backend `TenantRole`). */
export type TenantRole = "org_owner" | "org_admin" | "recruiter" | "member";

/** Membership lifecycle status (mirrors backend `MembershipStatus`). */
export type MembershipStatus = "invited" | "active" | "suspended";

/**
 * The active company context: a flattened view of one of the user's
 * memberships. `id`/`name`/`slug` identify the Company; `role`/`status` describe
 * the acting user's Membership in it. A user may hold many of these across
 * multiple companies (R2.11).
 */
export interface CompanyMembership {
  /** Stable Company identifier (R1.1, R18.4). */
  id: string;
  name: string;
  slug: string;
  /** Company's single market — informational only; tenant never derives from it. */
  market?: MarketKey;
  role: TenantRole;
  status: MembershipStatus;
}

/** localStorage key for the user's last selected active company. */
export const ACTIVE_COMPANY_STORAGE_KEY = "employed_active_company";

/** A membership grants tenant permissions only while it is active (R2.10). */
export function isActiveMembership(membership: CompanyMembership): boolean {
  return membership.status === "active";
}

/** Active memberships only — the set a user can act through. */
export function activeMemberships(memberships: CompanyMembership[]): CompanyMembership[] {
  return memberships.filter(isActiveMembership);
}

/** Find a membership by company id, if present. */
export function findMembership(
  memberships: CompanyMembership[],
  companyId: string | null | undefined,
): CompanyMembership | null {
  if (!companyId) {
    return null;
  }
  return memberships.find((membership) => membership.id === companyId) ?? null;
}

/**
 * Select the active company from a user's memberships.
 *
 * Preference order:
 * 1. The stored selection, when it still maps to an active membership.
 * 2. The first active membership.
 * 3. `null` when the user has no active memberships (e.g. a pure job seeker —
 *    R12 — or a user with only invited/suspended memberships).
 */
export function selectActiveCompany(
  memberships: CompanyMembership[],
  storedCompanyId?: string | null,
): CompanyMembership | null {
  const stored = findMembership(memberships, storedCompanyId);
  if (stored && isActiveMembership(stored)) {
    return stored;
  }

  return activeMemberships(memberships)[0] ?? null;
}

/** Read the last selected active company id (browser only). */
export function getStoredActiveCompanyId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(ACTIVE_COMPANY_STORAGE_KEY);
}

/** Persist (or clear) the selected active company id (browser only). */
export function setStoredActiveCompanyId(companyId: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (companyId) {
    window.localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, companyId);
  } else {
    window.localStorage.removeItem(ACTIVE_COMPANY_STORAGE_KEY);
  }
}
