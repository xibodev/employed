---
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: multi-tenant-hiring-platform spec — task 19.1 documentation sweep
---

# Verification & Trust — Employed

Trust is modelled as (a) a single, reusable **verification state machine** that
serves every verifiable entity, and (b) a set of **composable, named trust
badges** derived from underlying conditions — never a single opaque numeric
score.

Sources: `backend/app/services/verification.py`, `backend/app/services/trust.py`,
`backend/app/services/companies.py`, `backend/app/routers/verification.py`,
`backend/app/models/enums.py` (`VerificationState`).

## Verification state machine (DD-4)

A single `VerificationState` enum and one `transition()` function serve the
`Company`, `User` identity, `Profile`, and `Job` publication entities (each
carries a `verification_status` column, default `unverified`).

States: `unverified`, `pending`, `verified`, `rejected`, `revoked`, `flagged`.

```
            begin verification
 unverified ───────────────────▶ pending
     │                              │  approve (verify perm) ─▶ verified
     │ mark_review                  │  reject  (verify perm) ─▶ rejected
     ▼                              │
  flagged ◀───────── mark_review ───┤
     │                              │
     │ begin verification           ▼
     └──────────▶ pending      verified ── revoke (verify perm) ─▶ revoked
                                    └────── mark_review ─────────▶ flagged
 rejected ── resubmit ─▶ pending
 revoked  ── resubmit ─▶ pending
```

`transition(db, *, entity, target_state, actor, reason=None)`:

1. validates the transition against `ALLOWED_TRANSITIONS` — an illegal
   transition raises `IllegalTransitionError` (mapped to **`409`** at the
   router) and changes nothing;
2. applies the new state;
3. reconciles the entity's trust badges (see below);
4. writes exactly **one** append-only `AuditLog` row.

All four steps run atomically within the request transaction.

## Trust badges (DD-5)

Badges are computed from conditions and attached/removed as those conditions
change. `trust.derive_badges(entity)` is a pure function returning the set of
badges that *should* be attached; `trust.reconcile_badges(db, entity)` attaches
badges whose condition holds and removes badges whose condition no longer holds.

Supported badge sets:

| Entity | Badges |
|--------|--------|
| Company | `email verified`, `domain verified`, `business-document verified`, `payment verified`, `activity` |
| Job | `posted by verified company`, `salary disclosed`, `responsive` |
| Profile | `email verified`, `identity verified`, `phone verified` |

Company badges are persisted in the `companies.trust_badges` JSONB list and kept
in sync by `reconcile_badges` (called from `transition()` and from domain
verification).

## Company domain verification (R9)

Domain verification is the **priority trust anchor**; manual business-document
review is a later, higher tier. Two self-serve proofs are supported
(`services/companies.py`):

- **DNS TXT** — `verify_domain_via_dns(db, company, domain, expected_token)`
  checks for the expected TXT record.
- **Matching member emails** — `verify_domain_via_member_emails(db, company,
  domain)` confirms active members hold email addresses on the claimed domain.

On success the verified domain is appended to `verified_email_domains` and the
`domain verified` badge is attached. The domain-attach step is retried so a
list-write failure never discards a successful verification. A failed proof is
surfaced as **`422`** and changes nothing.

Manual **business-document** verification moves the company to `pending`, and a
holder of `company:verify` approving the document attaches the
`business-document verified` badge — each decision writes an audit entry.

## Publication moderation (R11)

Platform moderators drive marketplace trust through the `/moderation` router:

- **block** → sets a job's publication `status` to `flagged` (a non-`active`
  state) so the public listing/detail queries exclude it; writes a `job.block`
  audit row.
- **unpublish** → sets `status` to `inactive`; writes a `job.unpublish` audit row.
- **mark_review** → `verification_status` → `flagged` via the state machine.
- **verify** (job / company / profile) → `verification_status` → `verified` via
  the state machine.

Public visibility is enforced by the existing `status == "active"` filter on the
`/jobs` and `/api/jobs` queries, so blocked/unpublished jobs are never returned.

## Audit trail (R22)

Every privileged, verification, and moderation action writes exactly one
append-only `AuditLog` row (`services/audit.py`) capturing `actor` (or
`actor_label` for system actors), `action`, `target_type`, `target_id`,
`before`, and `after`. `AuditLog` and `ProfileVersion` have `before_update`
SQLAlchemy guards that raise on any mutation attempt; there is no update/delete
path in the service layer. The legacy `Job.status_history` JSONB pattern is
backfilled into the audit trail by migration `005` (see MIGRATION_STRATEGY.md).

See also: RBAC_AND_TENANCY.md, DATA_MODEL.md, API_MAP.md.
