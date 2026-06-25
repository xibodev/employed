"""Company tenant service (R1, R2.4/2.5).

Creating a company is a single atomic unit of work: the ``Company`` row, its
market-unique ``slug``, and the creating user's ``org_owner``/``active``
``Membership`` are written together. If the owner membership cannot be inserted
the company is rolled back so a tenant never exists without an owner (R2.5).

The data layer is the synchronous ``Session`` (DD-10): this module flushes
within the caller's transaction and never commits, leaving commit/rollback
semantics to the request boundary. A ``SAVEPOINT`` (nested transaction) isolates
the membership insert so its failure does not poison the surrounding
transaction.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from slugify import slugify
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import MarketKey, MembershipStatus, TenantRole, VerificationState
from app.models.membership import Membership
from app.models.user import User
from app.services.trust import reconcile_badges

# Company columns a caller may seed at creation time beyond the required
# name/market. Required columns and managed columns (slug, verification_status,
# created_by, the JSONB defaults) are handled explicitly and are not accepted as
# free-form optional fields.
_OPTIONAL_COMPANY_FIELDS: tuple[str, ...] = (
    "description",
    "logo_url",
    "website",
    "verified_email_domains",
    "external_refs",
)

# Fallback stem when a name slugifies to an empty string (e.g. a name made up
# entirely of characters slugify strips, such as punctuation or some scripts).
_EMPTY_SLUG_FALLBACK = "company"

# Guard against pathological collision loops; the numeric suffix space is large
# in practice, this only bounds a degenerate case.
_MAX_SLUG_ATTEMPTS = 10_000


def _slug_exists(db: Session, *, market: MarketKey, slug: str) -> bool:
    """Return ``True`` if *slug* is already taken within *market* (R1.3)."""
    stmt = sa.select(Company.id).where(Company.market == market, Company.slug == slug).limit(1)
    return db.execute(stmt).first() is not None


def generate_unique_slug(db: Session, name: str, market: MarketKey) -> str:
    """Generate a slug for *name* that is unique within *market* (R1.3).

    The name is slugified (lower-cased, accents folded, non-ASCII transliterated,
    separators normalised to ``-``). On collision within the market a short
    numeric suffix (``-2``, ``-3``, ...) is appended until the slug is free.
    Uniqueness is scoped to the market, mirroring
    ``UniqueConstraint(market, slug)`` on ``companies``.
    """
    base = slugify(name) or _EMPTY_SLUG_FALLBACK

    if not _slug_exists(db, market=market, slug=base):
        return base

    for suffix in range(2, _MAX_SLUG_ATTEMPTS + 2):
        candidate = f"{base}-{suffix}"
        if not _slug_exists(db, market=market, slug=candidate):
            return candidate

    raise RuntimeError(f"Unable to generate a unique slug for {name!r} in market {market!r}")


def create_company(
    db: Session,
    *,
    name: str,
    market: MarketKey,
    created_by: UUID,
    **optional_fields: Any,
) -> Company:
    """Create a Company plus its owner Membership atomically (R1.3/1.4/1.5, R2.4/2.5).

    The new company records ``created_by`` (R1.4), defaults to
    ``verification_status=unverified`` (R1.5), and is assigned a slug unique
    within *market* (R1.3). In the same transaction a ``Membership`` linking the
    creating user to the company with role ``org_owner`` and status ``active`` is
    created (R2.4). The membership insert runs inside a ``SAVEPOINT``; if it
    fails the company insert is rolled back with it so no ownerless company
    persists (R2.5).

    The work flushes within the caller's transaction (DD-10); the caller owns the
    final commit. Returns the persisted ``Company``.
    """
    unknown = set(optional_fields) - set(_OPTIONAL_COMPANY_FIELDS)
    if unknown:
        raise TypeError(f"Unexpected company fields: {', '.join(sorted(unknown))}")

    slug = generate_unique_slug(db, name, market)

    company = Company(
        name=name,
        slug=slug,
        market=market,
        created_by=created_by,
        verification_status=VerificationState.unverified,
    )
    for field in _OPTIONAL_COMPANY_FIELDS:
        if field in optional_fields and optional_fields[field] is not None:
            setattr(company, field, optional_fields[field])

    # Both inserts share one SAVEPOINT so that, if the owner-membership insert
    # fails, rolling back the nested transaction discards the company as well
    # (R2.5) — without poisoning the caller's outer transaction. The company is
    # flushed first inside the savepoint to obtain ``company.id`` for the FK.
    try:
        with db.begin_nested():
            db.add(company)
            db.flush()  # assign company.id before the membership references it

            membership = Membership(
                user_id=created_by,
                company_id=company.id,
                role=TenantRole.org_owner,
                status=MembershipStatus.active,
            )
            db.add(membership)
            db.flush()
    except SQLAlchemyError:
        # The SAVEPOINT rollback undid both inserts; expunge the company so the
        # rolled-back tenant is not re-flushed when the caller commits.
        if company in db:
            db.expunge(company)
        raise

    return company


# --- Domain verification (R9) ------------------------------------------------
#
# Domain verification is the priority verification anchor (R9.6): a low-friction,
# self-serve proof that a tenant controls a domain, earning the "domain verified"
# trust badge. Two proof methods are supported (R9.1/9.2):
#
#   * a DNS TXT record carrying an expected verification token, and
#   * an active member whose verified email address is on the claimed domain.
#
# On success both paths converge on a single attach step that appends the domain
# to ``verified_email_domains`` (R9.5) and reconciles trust badges so the
# "domain verified" badge attaches (R9.3 — the badge derives from a non-empty
# ``verified_email_domains``, see ``app.services.trust``).
#
# Per R9.4 the verification *result* must never be discarded by a failure to
# write the domain list: verification is decided first (it is deterministic and
# re-checkable), and the list append is a separate, idempotent step retried under
# its own SAVEPOINT so a transient list-write failure does not poison the
# caller's transaction or lose the proven verification.

# Bound the retry of the (idempotent) domain-list append (R9.4).
_DOMAIN_ATTACH_MAX_ATTEMPTS = 3

# A DNS TXT resolver maps a domain name to the TXT record strings published for
# it. Kept injectable so tests can supply a stub and so the heavy DNS dependency
# stays lazy/optional (the default resolver below).
DnsTxtResolver = Callable[[str], Iterable[str]]


def _normalize_domain(domain: str) -> str:
    """Normalise a claimed domain to its canonical, comparable form.

    Lower-cases, trims surrounding whitespace, and strips a leading ``@`` (as a
    bare ``@example.com`` may be passed) so comparisons against email domains and
    stored entries are stable.
    """
    return domain.strip().lstrip("@").lower()


def _email_domain(email: str) -> str:
    """Return the lower-cased domain part of an email address (``""`` if none)."""
    _, _, domain = email.partition("@")
    return domain.strip().lower()


def _default_dns_txt_resolver(domain: str) -> list[str]:
    """Resolve TXT records for *domain* using ``dnspython`` if it is installed.

    DNS is an optional/heavy dependency: it is imported lazily so importing this
    module never requires it, and callers that inject their own resolver (tests,
    or a different DNS client) never touch it. If a real lookup is attempted
    without ``dnspython`` available, a clear error explains how to proceed.
    """
    try:
        import dns.resolver  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised only without dnspython
        raise RuntimeError(
            "DNS TXT domain verification requires the 'dnspython' package or an injected resolver (pass resolver=...)."
        ) from exc

    answers = dns.resolver.resolve(domain, "TXT")
    records: list[str] = []
    for rdata in answers:
        for chunk in rdata.strings:
            records.append(chunk.decode() if isinstance(chunk, bytes) else str(chunk))
    return records


def _attach_verified_domain(db: Session, *, company: Company, domain: str) -> None:
    """Append *domain* to ``verified_email_domains`` and reconcile badges (R9.3/9.5).

    The append is idempotent (a domain already present is not duplicated) and the
    "domain verified" badge attaches via :func:`reconcile_badges` once the list is
    non-empty. The write runs inside a ``SAVEPOINT`` and is retried up to
    ``_DOMAIN_ATTACH_MAX_ATTEMPTS`` times so a transient list-write failure does
    not poison the caller's transaction nor discard the (already proven)
    verification (R9.4). If every attempt fails the last error is re-raised; the
    verification remains valid and re-checkable, so the attach can be retried by a
    subsequent call.
    """
    normalized = _normalize_domain(domain)
    last_error: SQLAlchemyError | None = None

    for _attempt in range(_DOMAIN_ATTACH_MAX_ATTEMPTS):
        try:
            with db.begin_nested():
                if normalized not in company.verified_email_domains:
                    company.verified_email_domains.append(normalized)
                reconcile_badges(db, company)
            return
        except SQLAlchemyError as exc:
            # The SAVEPOINT rolled back this attempt's write without poisoning the
            # outer transaction; retain the verification and retry the append.
            last_error = exc

    assert last_error is not None  # loop ran at least once
    raise last_error


def verify_domain_via_dns(
    db: Session,
    *,
    company: Company,
    domain: str,
    expected_token: str,
    resolver: DnsTxtResolver = _default_dns_txt_resolver,
) -> bool:
    """Verify *domain* for *company* via a DNS TXT record (R9.1).

    Resolves the TXT records for the claimed domain through *resolver* (injectable
    for testing and to keep the DNS dependency optional) and checks whether
    *expected_token* is published among them. On a match the domain is attached to
    the company and the trust badge reconciled (R9.3/9.5); the function returns
    ``True``. A non-matching domain returns ``False`` and changes nothing.
    """
    normalized = _normalize_domain(domain)
    records = resolver(normalized) or []
    verified = any(expected_token == str(record).strip() for record in records)
    if not verified:
        return False

    _attach_verified_domain(db, company=company, domain=normalized)
    return True


def verify_domain_via_member_emails(db: Session, *, company: Company, domain: str) -> bool:
    """Verify *domain* for *company* via a matching active member email (R9.2).

    Considers active memberships of *company* whose user has a verified email
    address on the claimed domain. If at least one such member exists the domain
    is attached and the trust badge reconciled (R9.3/9.5) and the function returns
    ``True``; otherwise it returns ``False`` and changes nothing.
    """
    normalized = _normalize_domain(domain)

    stmt = (
        sa.select(User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.company_id == company.id,
            Membership.status == MembershipStatus.active,
            User.email_verified.is_(True),
        )
    )
    emails = db.execute(stmt).scalars().all()
    verified = any(_email_domain(email) == normalized for email in emails)
    if not verified:
        return False

    _attach_verified_domain(db, company=company, domain=normalized)
    return True
