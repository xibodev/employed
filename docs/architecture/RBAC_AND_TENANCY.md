---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: multi-tenant-hiring-platform spec — task 19.1 documentation sweep
---

# RBAC & Tenancy — Employed

The hiring-platform evolution adds multi-tenancy (a `Company` tenant and a
`Membership` join) and a two-layer, permission-based authorization model on top
of the existing JWT auth and subdomain market resolution. Market (geography /
locale / payment) and tenant (organization / permission boundary) are treated as
**orthogonal axes** — neither is derived from the other.

Sources: `backend/app/services/rbac.py`, `backend/app/models/company.py`,
`backend/app/models/membership.py`, `backend/app/middleware/market.py`,
`backend/alembic/versions/003_rbac_and_tenancy.py`.

## Two axes: market vs tenant

| Axis | Resolved from | Carries | Where |
|------|---------------|---------|-------|
| **Market** | request hostname (first label) | geography, locale, payment providers | `MarketMiddleware` → `request.state.market`; mirrored in `frontend/src/lib/market.ts` |
| **Tenant** | the target resource's `company_id` + the acting user's `Membership` | organization identity, permission boundary | `rbac.require_permission` resolves per-action; `frontend/src/lib/tenant.ts` exposes the active company context |

A `Company` is scoped to a **single market** (`Company.market`), and a job posted
on behalf of a company must reference a company in the job's market. Cross-market
companies are deferred (Open Decision 2). The two axes never derive from each
other — the tenant is never read from the hostname, and the market is never read
from a membership.

## Permissions are the authorization primitive (DD-1)

Authorization always tests for a **permission string** (e.g. `job:moderate`),
never a role name. Roles are static bundles of permissions resolved at check
time, so role definitions stay data rather than branching logic.

### Permission catalog (`PERMISSION_CATALOG`)

Platform-scoped (moderation / verification / platform admin):

| Permission | Meaning |
|------------|---------|
| `job:moderate` | umbrella moderation capability |
| `job:block` | block a publication from public visibility |
| `job:unpublish` | stop a publication (→ `inactive`) |
| `job:mark_review` | flag a publication's verification state |
| `job:verify` | verify a publication |
| `company:verify` | verify a company |
| `profile:verify` | verify a profile |
| `user:suspend` | suspend a user |
| `platform_user:create` | create a platform user |
| `platform_role:assign` | assign platform roles |

Tenant-scoped (referenced by jobs, memberships, applications):

| Permission | Meaning |
|------------|---------|
| `job:post` | post a job on behalf of the company |
| `company:manage` | manage company settings + webhook endpoints |
| `company:manage_members` | invite / accept / suspend / list members |
| `company:verify_domain` | run domain verification for the company |
| `application:review` | list a company's applications |
| `application:advance` | change an application's pipeline status |

### Role → permission bundles

Platform roles act across **all** tenants (`PLATFORM_ROLE_PERMISSIONS`):

| Platform role | Permissions |
|---------------|-------------|
| `platform_super_admin` | the entire catalog |
| `platform_moderator` | `job:moderate/block/unpublish/mark_review/verify`, `company:verify`, `profile:verify`, `user:suspend` |
| `platform_support` | none by default |

Tenant roles are scoped to a single company (`TENANT_ROLE_PERMISSIONS`):

| Tenant role | Permissions |
|-------------|-------------|
| `org_owner` | `company:manage`, `company:manage_members`, `company:verify_domain`, `job:post`, `application:review`, `application:advance` |
| `org_admin` | `company:manage_members`, `company:verify_domain`, `job:post`, `application:review`, `application:advance` |
| `recruiter` | `job:post`, `application:review`, `application:advance` |
| `member` (viewer) | none (read-only) |

Platform roles live in the existing `users.roles` `text[]` column; tenant roles
live on `memberships.role`. Legacy free-form role strings that do not map to a
`PlatformRole` are ignored by the resolver (the RBAC migration remaps legacy
`admin` → `platform_super_admin`, see MIGRATION_STRATEGY.md).

## Effective permissions (DD-2/DD-3)

`effective_permissions(db, user, company_id)` returns the **union** of:

1. **Platform permissions** — every recognized `PlatformRole` on `user.roles`
   (these act across all tenants), and
2. **Tenant permissions** — those granted by the user's **active** membership in
   `company_id`.

Key rules enforced in `rbac.py`:

- Only an **`active`** membership contributes tenant permissions. `invited` and
  `suspended` memberships grant **none**, regardless of role.
- Tenant scope is resolved from the **owning company** of the target resource, so
  a user's memberships in *other* companies never affect a check.
- Either layer can authorize a tenant-scoped action on its own — a platform
  moderator needs no membership, and a company recruiter needs no platform role.
- When `company_id` is `None`, only platform permissions are returned.

```
authorize(user, P, resource):
    company_id = owning_company(resource)            # path/query/body
    perms = platform_perms(user)                     # union over PlatformRoles
    if company_id is not None:
        perms |= tenant_perms(active_membership(user, company_id))
    return P in perms                                # else 403
```

### `require_permission` dependency

`require_permission(permission, *, tenant_param="company_id")` is a FastAPI
dependency factory. It resolves the owning `company_id` from the target resource
— path params first, then query params, then the JSON body — and raises a
**generic `403`** when the permission is absent. The error detail never leaks
which company or permission was missing.

## Company & Membership model

`Company` (tenant entity): `name`, `slug` (unique within `market`), `market`,
`description`, `logo_url`, `website`, `verification_status` (default
`unverified`), `created_by`, `verified_email_domains` (JSONB list),
`trust_badges` (JSONB list), `external_refs` (JSONB). See DATA_MODEL.md.

`Membership` (join entity): `user_id`, `company_id`, `role` (`TenantRole`),
`status` (`MembershipStatus`), `invited_by`. `UniqueConstraint(user_id,
company_id)` means one membership per user/company pair; a user may hold
memberships across multiple companies (Open Decision 1). There is **no** company
FK on `User` — the relationship is expressed solely as a `Membership` row.

### Lifecycle invariants

- **Creating a company** writes the company and an `org_owner` / `active`
  membership for the creator in one transaction; if the membership insert fails,
  the company creation rolls back (no orphan company).
- **Invite** creates an `invited` membership and records `invited_by`.
- **Accept** moves `invited` → `active`; a failed/!invited accept leaves the
  status unchanged (mapped to `409`).
- **Suspend** sets the status to `suspended`, which immediately removes all
  tenant permissions that membership's role would grant.
- **Domain auto-membership** (on email verification, when the verified domain
  matches a company's `verified_email_domains`) is idempotent: it updates the
  existing row rather than duplicating, creates new rows as `invited` (manual
  approval still required), and writes an audit entry.

## Where this is wired

- Services: `rbac.py`, `companies.py`, `memberships.py`.
- Routers (all guarded by `require_permission`): `companies.py`,
  `memberships.py`, `applications.py`, `verification.py`, `webhooks_admin.py`.
- Frontend tenant context: `frontend/src/lib/tenant.ts` (kept separate from
  `market.ts`).

See also: VERIFICATION_AND_TRUST.md, INTEGRATION_AND_EXPORT.md,
MIGRATION_STRATEGY.md, DATA_MODEL.md, API_MAP.md.
