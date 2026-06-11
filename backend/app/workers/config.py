from arq.connections import RedisSettings

from app.config import settings
from app.workers.cron import cron_jobs
from app.workers.tasks import settle_simulated_intent


def _setting(name: str, default=None):
    # Fall through to the default when the Settings field exists but is None
    # (previously getattr returned the None value and RedisSettings.from_dsn
    # blew up at import time when REDIS_URL was unset).
    value = getattr(settings, name.lower(), None)
    if value in (None, ""):
        value = getattr(settings, name, None)
    if value in (None, ""):
        value = default
    return value


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(_setting("REDIS_URL", "redis://localhost:6379/0"))
    functions = [settle_simulated_intent]
    cron_jobs = cron_jobs
    max_jobs = 10
    job_timeout = 300
