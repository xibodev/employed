# Employed — Product Positioning

```yaml
last_verified: 2026-06-16T00:00:00Z
verified_by: multi-tenant-hiring-platform spec — task 19.1 documentation sweep
scope: hiring-platform evolution (multi-tenant-hiring-platform spec)
```

## One line

**More than a job board, less than a heavy ATS.** Employed lets organizations
reliably hire people in localized markets without the overhead of a full
Applicant Tracking System — while staying exportable *into* one.

## Where we sit

```
 classifieds / free        Employed                 full ATS
 job boards          (trust + light pipeline)   (Greenhouse, Lever, …)
 ─────────────────●────────────●────────────────────●─────────────▶
   no verification,         verification badges,        heavy workflow,
   no pipeline,             a lightweight, exportable   per-seat pricing,
   easy to spam             applications pipeline        migration lock-in
```

The original product is a multilingual, subdomain-localized job board for
**Mozambique (MZ)** and **Mexico (MX)**: companies post roles, candidates browse
active opportunities, admins moderate listings, and featured listings are paid
via Stripe / M-Pesa / e-Mola. That core is preserved unchanged. The
hiring-platform evolution layers two differentiators on top.

## Two differentiators

1. **Trust.** A per-entity verification state machine (`unverified → pending →
   verified / rejected / revoked / flagged`) and **composable, named trust
   badges** — never a single opaque score — signal that companies, jobs, and
   candidates are legitimate. Company domain verification (DNS TXT or matching
   member emails) is the low-friction anchor; manual business-document review is
   a higher tier.

2. **Portability / integration-readiness.** Standard schemas at every boundary
   (JSON Resume for candidates, schema.org `JobPosting` JSON-LD for jobs, a
   normalized Application object), an `external_refs` field on every major
   entity (map to external ATS ids with no migration), outbound webhooks for key
   events, and a versioned read-only export API. Data can move into a full ATS
   without a migration, so adopting Employed is never a lock-in decision.

## What this is NOT (deliberate scope boundaries)

- **Not a full ATS.** The applications pipeline is intentionally lightweight —
  five fixed stages (`applied → reviewed → shortlisted → rejected → hired`), list
  + kanban views, no complex workflow engine, scorecards, or per-seat billing.
- **Not a single-tenant tool.** Multi-tenancy (`Company` + `Membership`) and a
  two-layer RBAC model are first-class, but **market** (geography/locale/payment)
  and **tenant** (organization/permission boundary) stay orthogonal — a company
  belongs to one market; tenancy is never derived from the hostname.
- **Not lock-in.** Email-apply stays available alongside the tracked pipeline
  (applications default to tracked, but never silently fall back between
  channels). Everything is exportable.

## Markets & languages (unchanged)

- Markets resolved by subdomain: `mx.*` → MX, `mz.*` → MZ (default MZ).
- Locales: **`en`, `pt`, `es` only** (MX default `es`, MZ default `pt`).

See also: `USER_TYPES_AND_JOURNEYS.md`, `../architecture/RBAC_AND_TENANCY.md`,
`../architecture/VERIFICATION_AND_TRUST.md`,
`../architecture/INTEGRATION_AND_EXPORT.md`.
