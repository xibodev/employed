"""Property-based test for "application email tokens are fully substituted"
(Property 22).

Requirement 15.2 says that when an application email is generated, every token
in the template -- ``{job_title}``, ``{company}`` and ``{candidate_name}`` -- is
replaced with the corresponding value.
:func:`app.services.application_email.render_application_email` implements this
with explicit :py:meth:`str.replace` (not ``str.format``) so values that contain
brace characters cannot crash rendering.

The property under test (R15.2 / Property 22): for any values of ``job_title``,
``company`` and ``candidate_name``, the rendered email (subject + body)

1. contains each provided value verbatim, and
2. contains no unresolved token placeholder (no ``{job_title}``, ``{company}``
   or ``{candidate_name}`` substring survives).

Input space note: the generated values deliberately span free-form Unicode,
accented/non-Latin scripts and brace characters -- the cases the
``str.replace`` design is meant to make safe. They are constrained to exclude
the *exact* literal token placeholders (``"{job_title}"`` etc.): a real job
title or candidate name is never literally another field's placeholder, and
feeding a value that *is* a placeholder is a self-referential case outside the
property's intended input space (it would both corrupt verbatim preservation
through substitution order and masquerade as an "unresolved" placeholder).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.application_email import TOKEN_NAMES, render_application_email

# The literal placeholders the template carries and the renderer must consume.
_TOKEN_PLACEHOLDERS: tuple[str, ...] = tuple("{" + token + "}" for token in TOKEN_NAMES)


def _has_no_token_placeholder(value: str) -> bool:
    """True when *value* does not itself contain any literal token placeholder."""

    return not any(placeholder in value for placeholder in _TOKEN_PLACEHOLDERS)


# Free-form Unicode (incl. braces, which live in the printable ASCII range and
# the broader BMP range below), excluding surrogate code points.
_unicode_text = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=0x2FFF, blacklist_categories=("Cs",)),
    min_size=1,
    max_size=60,
)
# Values that specifically exercise brace handling (the reason str.replace is
# used instead of str.format): unmatched, doubled, and embedded braces.
_brace_samples = st.sampled_from(
    [
        "Senior {Dev}",
        "C{o}mpany",
        "{unmatched",
        "matched}",
        "{{double}}",
        "Ana {María}",
        "R&D {Team}",
        "{}",
        "a{b}c",
        "100% {growth}",
    ]
)
# Accented Latin and non-Latin scripts to confirm Unicode round-trips intact.
_unicode_samples = st.sampled_from(
    [
        "Café Société",
        "日本株式会社",
        "Москва ООО",
        "Niño Über",
        "한국 회사",
        "شركة الأمل",
        "Ελλάδα ΑΕ",
        "Renée O'Brien",
        "José Müller",
        "Łódź Group",
    ]
)

_value = st.one_of(_unicode_text, _brace_samples, _unicode_samples).filter(_has_no_token_placeholder)


# Feature: multi-tenant-hiring-platform, Property 22: Application email tokens are fully substituted
@settings(max_examples=100, deadline=None)
@given(job_title=_value, company=_value, candidate_name=_value)
def test_application_email_tokens_are_fully_substituted(
    job_title: str,
    company: str,
    candidate_name: str,
) -> None:
    """For any ``job_title``/``company``/``candidate_name`` -- including Unicode
    and brace-containing values -- the rendered email contains each provided
    value verbatim and leaves no unresolved token placeholder.

    Validates: Requirements 15.2
    """

    rendered = render_application_email(
        job_title=job_title,
        company=company,
        candidate_name=candidate_name,
    )

    full_text = f"{rendered.subject}\n{rendered.body}"

    # (1) Every provided value is substituted into the rendered email verbatim.
    for label, value in (
        ("job_title", job_title),
        ("company", company),
        ("candidate_name", candidate_name),
    ):
        assert value in full_text, f"value for {label!r} missing from rendered email: {value!r}"

    # (2) No token placeholder survives anywhere in subject or body.
    for placeholder in _TOKEN_PLACEHOLDERS:
        assert placeholder not in full_text, f"unresolved placeholder {placeholder!r} remained in rendered email"


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
