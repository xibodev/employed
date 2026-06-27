"""Observability bootstrap — Sentry error/performance tracking.

Call ``init_sentry()`` once at application startup (create_app).
When SENTRY_DSN is not set the function is a no-op so local and CI
environments are unaffected.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Initialise Sentry SDK if SENTRY_DSN is configured."""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.debug("observability.sentry: SENTRY_DSN not set — skipping init")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        logger.warning("observability.sentry: sentry-sdk not installed — skipping init")
        return

    environment = os.getenv("SENTRY_ENVIRONMENT", "uat")
    traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=traces_sample_rate,
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
            # Do not send PII by default
            send_default_pii=False,
        )
    except Exception:  # noqa: BLE001 — observability must never take down the app
        logger.exception("observability.sentry: init failed — continuing without error tracking")
        return
    logger.info(
        "observability.sentry: initialised environment=%s traces_sample_rate=%s", environment, traces_sample_rate
    )
