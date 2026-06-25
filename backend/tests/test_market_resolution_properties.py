"""Property-based test for "Market resolution by subdomain is preserved" (Property 29).

The active market is derived from the first hostname label: ``mx.*`` -> MX,
``mz.*`` -> MZ, and anything else falls back to the default (``mz``). This holds
across registrable bases (``example.com``), the local-testing ``*.lvh.me`` form,
bare ``localhost``, and hostnames carrying an explicit port. In any split-host
topology the frontend sends the market hostname via ``X-Forwarded-Host``, which
must take precedence over the ``Host`` header (EMP-001).

These properties exercise the real resolution helpers
:func:`app.services.market.market_key_from_host` /
:func:`app.services.market.market_from_host` and the middleware's
``X-Forwarded-Host`` precedence helper, so no behavior is re-implemented here.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.middleware.market import _request_market_host
from app.services.market import (
    DEFAULT_MARKET_KEY,
    MARKETS,
    market_from_host,
    market_from_key,
    market_key_from_host,
)

# The two real markets resolved by subdomain (R24.4).
_MARKET_KEYS = sorted(MARKETS.keys())  # ["mx", "mz"]

# Bases a market label can be prefixed onto: a registrable domain, the local
# testing domain (*.lvh.me), the project domain, and a generic split-host base.
_BASES = st.sampled_from(
    [
        "example.com",
        "lvh.me",
        "employed.co.mz",
        "employed.example",
        "foo.bar.baz",
    ]
)

# Optional port suffix; the resolver must ignore the port entirely.
_PORTS = st.sampled_from(["", ":3000", ":8000", ":80", ":443"])

_MARKET = st.sampled_from(_MARKET_KEYS)


def _vary_case(draw: st.DrawFn, value: str) -> str:
    """Randomly upper/lower each character so casing never changes the result."""
    flags = draw(st.lists(st.booleans(), min_size=len(value), max_size=len(value)))
    return "".join(ch.upper() if flag else ch.lower() for ch, flag in zip(value, flags))


@st.composite
def _market_hosts(draw: st.DrawFn) -> tuple[str, str]:
    """Build a ``{market}.{base}[:port]`` host and return (host, expected_key)."""
    market = draw(_MARKET)
    base = draw(_BASES)
    port = draw(_PORTS)
    host = _vary_case(draw, f"{market}.{base}") + port
    return host, market


class _Headers:
    """Minimal case-insensitive headers stub mirroring Starlette's ``.get``."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._m = {k.lower(): v for k, v in mapping.items()}

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._m.get(key.lower(), default)


class _Request:
    """Just enough of a request for ``_request_market_host`` (reads headers)."""

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = _Headers(headers)


# Feature: multi-tenant-hiring-platform, Property 29: Market resolution by subdomain is preserved
@settings(max_examples=100, deadline=None)
@given(case=_market_hosts())
def test_subdomain_resolves_to_its_market(case: tuple[str, str]) -> None:
    """For any ``mz``/``mx`` hostname (any base, any port, any casing), the
    resolver returns that market key and its market record.

    Validates: Requirements 24.4
    """
    host, expected_key = case

    assert market_key_from_host(host) == expected_key
    assert market_from_host(host) == MARKETS[expected_key]
    # The resolved record is internally consistent.
    assert market_from_host(host)["key"] == expected_key


# Feature: multi-tenant-hiring-platform, Property 29: Market resolution by subdomain is preserved
@settings(max_examples=100, deadline=None)
@given(case=_market_hosts())
def test_lvh_me_forms_resolve_to_their_market(case: tuple[str, str]) -> None:
    """The local-testing ``{market}.lvh.me`` form (with optional port) resolves
    to the same market as any other base.

    Validates: Requirements 24.4
    """
    _host, expected_key = case
    port = _host.split(":", 1)[1] if ":" in _host else ""
    lvh_host = f"{expected_key}.lvh.me" + (f":{port}" if port else "")

    assert market_key_from_host(lvh_host) == expected_key
    assert market_from_host(lvh_host) == MARKETS[expected_key]


# Feature: multi-tenant-hiring-platform, Property 29: Market resolution by subdomain is preserved
@settings(max_examples=100, deadline=None)
@given(case=_market_hosts(), api_base=_BASES, port=_PORTS)
def test_x_forwarded_host_takes_precedence(case: tuple[str, str], api_base: str, port: str) -> None:
    """When ``X-Forwarded-Host`` carries the market hostname, it wins over a
    non-market ``Host`` (e.g. ``api.*``), and the first value of a comma chain
    is used.

    Validates: Requirements 24.4
    """
    market_host, expected_key = case
    api_host = f"api.{api_base}{port}"  # first label is never a market key

    # X-Forwarded-Host alone determines the market.
    req = _Request({"Host": api_host, "X-Forwarded-Host": market_host})
    assert market_from_host(_request_market_host(req)) == MARKETS[expected_key]

    # Only the first entry of a comma-separated chain is honoured.
    chained = _Request({"Host": api_host, "X-Forwarded-Host": f"{market_host}, proxy.internal{port}"})
    assert market_from_host(_request_market_host(chained)) == MARKETS[expected_key]


# Feature: multi-tenant-hiring-platform, Property 29: Market resolution by subdomain is preserved
@settings(max_examples=100, deadline=None)
@given(case=_market_hosts())
def test_empty_x_forwarded_host_falls_back_to_host(case: tuple[str, str]) -> None:
    """An empty/whitespace ``X-Forwarded-Host`` is ignored and resolution falls
    back to the market-bearing ``Host`` header.

    Validates: Requirements 24.4
    """
    market_host, expected_key = case

    for forwarded in ("", "   ", " , proxy.internal"):
        req = _Request({"Host": market_host, "X-Forwarded-Host": forwarded})
        assert market_from_host(_request_market_host(req)) == MARKETS[expected_key]


# Feature: multi-tenant-hiring-platform, Property 29: Market resolution by subdomain is preserved
@settings(max_examples=100, deadline=None)
@given(
    label=st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=12),
    base=_BASES,
    port=_PORTS,
)
def test_non_market_subdomain_defaults(label: str, base: str, port: str) -> None:
    """Any first label that is not a known market resolves to the default market,
    confirming the mz/mx contract is exact (no accidental matches).

    Validates: Requirements 24.4
    """
    if label in MARKETS:
        return  # only assert over the non-market space

    host = f"{label}.{base}{port}"
    assert market_key_from_host(host) == DEFAULT_MARKET_KEY
    assert market_from_host(host) == market_from_key(None)


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
