from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.market import market_from_host, market_from_key


def _request_market_host(request: Request) -> str | None:
    """Resolve the market host, preferring X-Forwarded-Host over Host.

    The frontend API client deliberately sends X-Forwarded-Host with the
    market hostname because in any split-host topology (api.* serving mx.*/
    mz.* frontends) the Host header carries the API hostname, whose first
    label is never a market key (EMP-001). Mirrors the frontend's
    resolveMarketFromHeaders. Only the first value of a comma-separated
    X-Forwarded-Host chain is used.
    """
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        first = forwarded_host.split(",", 1)[0].strip()
        if first:
            return first
    return request.headers.get("host")


class MarketMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.market = market_from_host(_request_market_host(request))
        response = await call_next(request)
        response.headers.setdefault("X-Market", request.state.market["key"])
        return response


def get_current_market(request: Request) -> dict:
    return getattr(request.state, "market", market_from_key(None))
