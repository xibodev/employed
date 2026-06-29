---
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: multi-tenant-hiring-platform spec — task 19.1 documentation sweep
---

# Integration & Export — Employed

The platform is **integration-ready**: it exposes standard schemas at every
boundary, attaches external identifiers to every major entity without
migrations, emits outbound webhooks for domain events, and serves a versioned,
read-only export API. The goal is that data can move into a full ATS without a
migration.

Sources: `backend/app/services/export.py`, `backend/app/services/webhooks.py`,
`backend/app/services/external_refs.py`, `backend/app/workers/tasks.py`
(`deliver_webhook`), `backend/app/routers/export_api.py`,
`backend/app/routers/webhooks_admin.py`.

## Standard schemas at boundaries (R18)

`services/export.py` holds **pure, side-effect-free mappers** that read ORM
instances and return plain `dict` documents (safe to call from routers, workers,
and tests):

| Mapper | Output | Used for |
|--------|--------|----------|
| `to_json_resume(profile_or_version)` | [JSON Resume](https://jsonresume.org/) document | candidate export, PDF rendering |
| `to_job_posting_jsonld(job)` | schema.org [`JobPosting`](https://schema.org/JobPosting) JSON-LD | job export, SEO-friendly job data |
| `to_normalized_application(application)` | normalized Application object | application export |

The JobPosting mapper maps our `JobType` → schema.org `employmentType`, our
market country → ISO 3166-1 alpha-2 (`MX`/`MZ`) in the `jobLocation`
`PostalAddress`, and our `SalaryPeriod` → `QuantitativeValue.unitText`. The
`Base.id` UUID is the **stable public identifier** for every entity (R18.4).

## External references (R19)

Every major entity carries an `external_refs` JSONB column — `Company`, `Job`,
`Profile`, `User`, and `Application`. Integrators map platform records to
external ATS ids by writing into this dict; because it is JSONB, adding or
updating a mapping is a write, never a schema migration. Read/write helpers live
in `services/external_refs.py`.

## Webhooks for domain events (R20)

Outbound notifications keep an external system in sync. Events
(`WebhookEvent`): `job.published`, `application.created`,
`application.status_changed`.

### Registration

`WebhookEndpoint` rows register a receiver: `url`, `secret`, `events` (JSONB list
of subscribed events), `active`, and a nullable `company_id` (null ⇒
platform-level endpoint). Managed via the `/webhook-endpoints` router, guarded by
`company:manage`. The signing secret is never returned in responses.

### Emission (fan-out)

`emit(db, event, payload)` fans an event out to **exactly** the active endpoints
subscribed to it: it persists one `WebhookDelivery` row per subscribed endpoint
(status `pending`) and enqueues the `deliver_webhook` arq task per delivery.
Emission runs **after** the triggering business write is committed and never
rolls back that write — delivery rows persist within the caller's transaction and
enqueue failures are logged and swallowed (R16.7). `job.published` emission is
wired into job publication; `application.created` / `application.status_changed`
are emitted by the applications service.

### Delivery + retry (R20.5)

The `deliver_webhook` arq task POSTs the payload and signs it with an
`X-Webhook-Signature: sha256=<hmac>` header (HMAC-SHA256 over the canonical JSON
body using the endpoint secret). On failure it increments `attempts`, records
`last_error`, and either reschedules via bounded exponential backoff
(`next_attempt_at = now + min(2^attempts * 30s, 6h)`, staying `pending`) or, at
`WEBHOOK_MAX_ATTEMPTS` (10), transitions to the terminal `failed` state.
Delivery is idempotent — a `delivered`/`failed` delivery is never re-sent.

> These backoff knobs (`WEBHOOK_BACKOFF_BASE_SECONDS`, `WEBHOOK_BACKOFF_CAP`,
> `WEBHOOK_MAX_ATTEMPTS`, `WEBHOOK_DELIVERY_TIMEOUT_SECONDS`) are **module
> constants** in `app/workers/tasks.py`, not environment variables.

## Versioned export API (R21)

`/export/v1` (router `export_api.py`) is read-only and requires a valid bearer
token. The version segment lives in the **path** (bump to `/export/v2` for
breaking changes). Route nouns follow HR Open Standards terminology where
feasible: an open role is a *PositionOpening*, so jobs are under `/positions`
(with a `/jobs` alias for schema.org parity).

| Method | Path | Returns |
|--------|------|---------|
| GET | `/export/v1/candidates/{id}` | candidate as JSON Resume (resolves a live `Profile` or a `ProfileVersion`) |
| GET | `/export/v1/positions/{id}` | job as schema.org `JobPosting` JSON-LD |
| GET | `/export/v1/jobs/{id}` | alias of `/positions/{id}` (hidden from schema) |
| GET | `/export/v1/applications/{id}` | normalized Application object |

A request for a nonexistent identifier returns **`404`** (R21.4).

## Profiles, versions, and PDF resumes (R13/R14)

A user has a single live `Profile` carrying a `json_resume` JSONB working copy.
Saving a version writes an immutable, append-only `ProfileVersion` snapshot with
a monotonic `version_number` (`profiles_versioning.py`). PDF resume rendering is
enqueued on the arq worker (`render_resume_pdf` → `resume_templates.py`), which
maps the version to JSON Resume, renders a predefined template (`classic`,
`modern`, `minimal`) to HTML, and writes a downloadable PDF artifact. The
HTML→PDF step uses `weasyprint`/`xhtml2pdf` if installed and otherwise falls back
to a self-contained text PDF writer. Artifacts are written under
`RESUME_ARTIFACT_DIR` (optional; defaults to a temp subdir) — see
CONFIG_AND_SECRETS_MAP.md.

See also: RBAC_AND_TENANCY.md, VERIFICATION_AND_TRUST.md, DATA_MODEL.md,
API_MAP.md.
