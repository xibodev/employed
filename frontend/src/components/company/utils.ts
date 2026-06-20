import type { CompanyMembership, MembershipStatus, TenantRole } from "@/lib/tenant";
import type { Company, MembershipStatusValue, TenantRoleValue, VerificationState } from "@/lib/types";

/** Flatten a {@link Company} plus the acting user's role/status into the tenant
 * context's {@link CompanyMembership} shape. */
export function companyToMembership(
  company: Company,
  role: TenantRole = "member",
  status: MembershipStatus = "active",
): CompanyMembership {
  return {
    id: company.id,
    name: company.name,
    slug: company.slug,
    market: company.market,
    role,
    status,
  };
}

/** Badge palette for a verification state, mapped to the shared `Badge` variants. */
export function verificationVariant(state: VerificationState): "default" | "success" | "warning" | "info" | "danger" {
  switch (state) {
    case "verified":
      return "success";
    case "pending":
      return "info";
    case "rejected":
    case "revoked":
    case "flagged":
      return "danger";
    default:
      return "default";
  }
}

/** Badge palette for a membership status. */
export function membershipStatusVariant(status: MembershipStatusValue): "default" | "success" | "warning" | "danger" {
  switch (status) {
    case "active":
      return "success";
    case "invited":
      return "warning";
    case "suspended":
      return "danger";
    default:
      return "default";
  }
}

/** Selectable tenant roles for invite/role controls. */
export const TENANT_ROLE_VALUES: TenantRoleValue[] = ["org_owner", "org_admin", "recruiter", "member"];
