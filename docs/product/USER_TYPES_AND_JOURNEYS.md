# Employed — User Types & Journeys

```yaml
last_verified: 2026-06-16T00:00:00Z
verified_by: multi-tenant-hiring-platform spec — task 19.1 documentation sweep
scope: hiring-platform evolution (multi-tenant-hiring-platform spec)
```

A `User` is just an authenticated account; the *types* below are roles a user
plays, and one user can play several. A user's relationship to a company is a
`Membership` row (tenant role), never a field on the user. Platform staff roles
live on `users.roles`. See `../architecture/RBAC_AND_TENANCY.md`.

## User types

### 1. Job seeker

Browses and applies to jobs with **no company membership required**. Owns a
single live `Profile` (JSON Resume) and can save immutable `ProfileVersion`
snapshots, download a PDF resume, and apply (tracked in-platform by default, or
by email/mailto).

### 2. Company member (tenant role)

A user with an **active** `Membership` in a `Company`. Tenant roles, in
decreasing privilege:

- **org_owner** — full company management, members, domain verification, posting,
  application review/advance. Created automatically for whoever creates the
  company.
- **org_admin** — manage members, verify domain, post, review/advance.
- **recruiter** — post jobs, review and advance applications.
- **member (viewer)** — read-only.

Only `active` memberships grant permissions; `invited` and `suspended` grant
none.

### 3. Platform staff (platform role)

Acts across **all** tenants. Roles on `users.roles`:

- **platform_super_admin** — entire permission catalog (legacy `admin` accounts
  are migrated here).
- **platform_moderator** — moderation + verification of jobs, companies,
  profiles, and users.
- **platform_support** — no privileged catalog actions by default.

## Key journeys

### Job seeker → apply

1. Browse market-scoped published jobs (no membership needed).
2. Build a profile; optionally save a `ProfileVersion` and download a PDF resume.
3. Apply: a tracked `Application` is created with status `applied`, referencing
   either the candidate user or a profile snapshot. The `application.created`
   webhook fires. Email/mailto remains available; the platform never silently
   falls back between channels.

### Company owner → stand up a tenant

1. Create a company → become its active `org_owner` (atomic with the company).
2. Verify the company domain (DNS TXT or matching member emails) → earn the
   `domain verified` badge; the domain is added to `verified_email_domains`.
3. Invite members (`invited` → they accept → `active`), or rely on domain
   auto-membership when teammates verify a matching work-email (created
   `invited`, still requiring approval).
4. Post jobs on behalf of the company (`job:post`); the job carries the company
   identity and trust signals.

### Recruiter → run the pipeline

1. List the company's applications (`application:review`) in list or kanban view.
2. Advance an application through `applied → reviewed → shortlisted → rejected /
   hired` (`application:advance`). Each change persists the new stage, writes an
   audit entry, and emits `application.status_changed`.

### Platform moderator → keep the marketplace trustworthy

1. Block / unpublish a job (removes it from public visibility).
2. Mark a job under review (`flagged`), or verify a job, company, or profile via
   the shared verification state machine.
3. Every action writes exactly one append-only audit-log entry.

### Integrator → move data out

1. Register a webhook endpoint subscribed to domain events.
2. Pull records from the versioned export API (`/export/v1`): candidates as JSON
   Resume, jobs as schema.org `JobPosting` JSON-LD, applications as a normalized
   object.
3. Map platform ids to external ATS ids via each entity's `external_refs` — no
   migration required.

See also: `POSITIONING.md`, `../architecture/RBAC_AND_TENANCY.md`,
`../architecture/INTEGRATION_AND_EXPORT.md`.
