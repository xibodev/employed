from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
import json

from tests.conftest import utcnow


class FakeStripeModule:
    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            return {
                "type": "checkout.session.completed",
                "data": {"object": {"id": "cs_test_1", "metadata": {}}},
            }


def test_stripe_webhook_with_valid_signature_returns_200(client, monkeypatch):
    monkeypatch.setattr("app.webhooks.stripe_webhook._setting", lambda name, default=None: "whsec_test")
    monkeypatch.setattr("app.webhooks.stripe_webhook._stripe_module", lambda: FakeStripeModule)

    response = client.post("/_stripe/webhook", content=b"{}", headers={"stripe-signature": "sig_test"})

    assert response.status_code == 200


def test_stripe_webhook_with_invalid_signature_returns_400(client, monkeypatch):
    class BrokenStripeModule:
        class Webhook:
            @staticmethod
            def construct_event(payload, signature, secret):
                raise ValueError("bad signature")

    monkeypatch.setattr("app.webhooks.stripe_webhook._setting", lambda name, default=None: "whsec_test")
    monkeypatch.setattr("app.webhooks.stripe_webhook._stripe_module", lambda: BrokenStripeModule)

    response = client.post("/_stripe/webhook", content=b"{}", headers={"stripe-signature": "sig_bad"})

    assert response.status_code == 400


def test_stripe_checkout_session_completed_settles_intent(
    client, monkeypatch, payment_intent_factory, sample_job, test_user, db_session
):
    job = sample_job(user=test_user, featured=False)
    intent = payment_intent_factory(job=job, user=test_user, status="pending")

    class SettlingStripeModule:
        class Webhook:
            @staticmethod
            def construct_event(payload, signature, secret):
                return {
                    "id": "evt_complete_1",
                    "type": "checkout.session.completed",
                    "data": {"object": {"id": "cs_complete_1", "metadata": {"intentId": intent.id}}},
                }

    monkeypatch.setattr("app.webhooks.stripe_webhook._setting", lambda name, default=None: "whsec_test")
    monkeypatch.setattr("app.webhooks.stripe_webhook._stripe_module", lambda: SettlingStripeModule)
    from app.webhooks.stripe_webhook import PROCESSED_STRIPE_EVENTS

    PROCESSED_STRIPE_EVENTS.clear()
    response = client.post("/_stripe/webhook", content=b"{}", headers={"stripe-signature": "sig_ok"})
    db_session.refresh(intent)
    db_session.refresh(job)

    assert response.status_code == 200
    assert intent.status == "completed"
    assert job.featured_through == intent.extended_through


def test_stripe_duplicate_event_is_ignored(client, monkeypatch):
    calls = {"count": 0}

    class DuplicateStripeModule:
        class Webhook:
            @staticmethod
            def construct_event(payload, signature, secret):
                return {
                    "id": "evt_duplicate_1",
                    "type": "checkout.session.completed",
                    "data": {"object": {"id": "cs_duplicate_1", "metadata": {"intentId": "intent-1"}}},
                }

    class DummyIntent:
        id = "intent-1"

    async def fake_settle_intent(db, intent_id, provider_ref=None):
        calls["count"] += 1
        return {"intent_id": intent_id, "provider_ref": provider_ref}

    monkeypatch.setattr("app.webhooks.stripe_webhook._setting", lambda name, default=None: "whsec_test")
    monkeypatch.setattr("app.webhooks.stripe_webhook._stripe_module", lambda: DuplicateStripeModule)
    monkeypatch.setattr("app.webhooks.stripe_webhook._find_intent_from_session", lambda db, payload: DummyIntent())
    monkeypatch.setattr("app.webhooks.stripe_webhook.settle_intent", fake_settle_intent)
    from app.webhooks.stripe_webhook import PROCESSED_STRIPE_EVENTS

    PROCESSED_STRIPE_EVENTS.clear()
    first = client.post("/_stripe/webhook", content=b"{}", headers={"stripe-signature": "sig_ok"})
    second = client.post("/_stripe/webhook", content=b"{}", headers={"stripe-signature": "sig_ok"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1


def test_mpesa_callback_with_valid_hmac_returns_200(client, monkeypatch, payment_intent_factory, sample_job, test_user):
    secret = "mpesa-secret"
    job = sample_job(user=test_user)
    intent = payment_intent_factory(
        job=job, user=test_user, provider_key="mpesa", status="awaiting_user", provider_ref="ref-123"
    )
    # timestamp is mandatory since EMP-019
    payload = {"provider_ref": intent.provider_ref, "status": "successful", "timestamp": utcnow().isoformat()}
    raw = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    monkeypatch.setattr("app.webhooks.mobile_money._setting", lambda name, default=None: secret)

    response = client.post("/_mpesa/callback", content=raw, headers={"x-mpesa-signature": signature})

    assert response.status_code == 200
    assert response.json()["updated"] is True


def test_mpesa_callback_with_invalid_hmac_returns_400(client, monkeypatch):
    monkeypatch.setattr("app.webhooks.mobile_money._setting", lambda name, default=None: "mpesa-secret")

    response = client.post(
        "/_mpesa/callback",
        content=b'{"provider_ref": "ref-1", "status": "successful"}',
        headers={"x-mpesa-signature": "bad-signature"},
    )

    assert response.status_code == 400


def test_mpesa_callback_rejects_stale_timestamp(client, monkeypatch):
    secret = "mpesa-secret"
    payload = {
        "provider_ref": "ref-stale",
        "status": "successful",
        "event_id": "mpesa-stale-1",
        "timestamp": (utcnow() - timedelta(minutes=10)).isoformat(),
    }
    raw = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    monkeypatch.setattr("app.webhooks.mobile_money._setting", lambda name, default=None: secret)
    from app.webhooks.mobile_money import PROCESSED_CALLBACK_EVENTS

    PROCESSED_CALLBACK_EVENTS.clear()
    response = client.post("/_mpesa/callback", content=raw, headers={"x-mpesa-signature": signature})

    assert response.status_code == 400
    assert response.json()["detail"] == "stale-webhook-payload"


def test_mpesa_duplicate_callback_is_ignored(client, monkeypatch):
    secret = "mpesa-secret"
    calls = {"count": 0}
    payload = {
        "provider_ref": "ref-duplicate",
        "intent_id": "intent-duplicate",
        "status": "successful",
        "event_id": "mpesa-duplicate-1",
        "timestamp": utcnow().isoformat(),
    }
    raw = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    class DummyIntent:
        id = "intent-duplicate"
        provider_ref = "ref-duplicate"

    async def fake_settle_intent(db, intent_id, provider_ref=None):
        calls["count"] += 1
        return {"intent_id": intent_id, "provider_ref": provider_ref}

    monkeypatch.setattr("app.webhooks.mobile_money._setting", lambda name, default=None: secret)
    monkeypatch.setattr("app.webhooks.mobile_money._find_intent", lambda db, provider_ref, intent_id: DummyIntent())
    monkeypatch.setattr("app.webhooks.mobile_money.settle_intent", fake_settle_intent)
    from app.webhooks.mobile_money import PROCESSED_CALLBACK_EVENTS

    PROCESSED_CALLBACK_EVENTS.clear()
    first = client.post("/_mpesa/callback", content=raw, headers={"x-mpesa-signature": signature})
    second = client.post("/_mpesa/callback", content=raw, headers={"x-mpesa-signature": signature})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["updated"] is True
    assert second.json()["updated"] is False
    assert calls["count"] == 1


def test_stripe_webhook_is_mounted_under_webhooks_prefix(client):
    """EMP-014 regression: the app mounts the webhook router under
    /webhooks, so the public path is POST /webhooks/_stripe/webhook.
    It must exist (not 404) — unconfigured secret yields 4xx/503."""
    response = client.post("/webhooks/_stripe/webhook", content=b"{}")

    assert response.status_code != 404
    assert response.status_code in (400, 401, 403, 503)


def test_mpesa_callback_rejects_missing_timestamp(client, monkeypatch):
    """EMP-019 regression: payloads without a timestamp skipped staleness
    validation entirely (unbounded replay window). Now mandatory."""
    secret = "mpesa-secret"
    payload = {
        "provider_ref": "ref-notimestamp",
        "intent_id": "intent-notimestamp",
        "status": "successful",
        "event_id": "mpesa-no-ts-1",
    }
    raw = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    monkeypatch.setattr("app.webhooks.mobile_money._setting", lambda name, default=None: secret)
    from app.webhooks.mobile_money import PROCESSED_CALLBACK_EVENTS

    PROCESSED_CALLBACK_EVENTS.clear()
    response = client.post("/_mpesa/callback", content=raw, headers={"x-mpesa-signature": signature})

    assert response.status_code == 400
    assert response.json()["detail"] == "missing-webhook-timestamp"


def test_replay_cache_uses_redis_when_available(monkeypatch):
    """EMP-019: dedupe keys live in Redis (shared, restart-surviving) when
    configured; the in-process map is only the fallback."""
    from app.webhooks.replay_cache import ReplayCache

    class FakeRedis:
        def __init__(self):
            self.store: dict[str, str] = {}
            self.ttls: dict[str, int] = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None):
            self.store[key] = value
            if ex is not None:
                self.ttls[key] = ex

        def close(self):
            pass

    shared = FakeRedis()
    monkeypatch.setattr("app.webhooks.replay_cache.redis_client", lambda: shared)

    # Two separate cache instances simulate two worker processes
    cache_a = ReplayCache(ttl_seconds=300, namespace="test-ns")
    cache_b = ReplayCache(ttl_seconds=300, namespace="test-ns")

    assert cache_a.contains("evt-1") is False
    cache_a.add("evt-1")
    assert cache_b.contains("evt-1") is True
    assert shared.ttls["replay:test-ns:evt-1"] == 300
