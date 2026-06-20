"""Property-based test for the audit entry-per-action invariant.

# Feature: multi-tenant-hiring-platform, Property 9: Every privileged action
# writes exactly one audit entry

Property 9 (design.md): *For any* sequence of privileged, verification, or
moderation actions, the platform writes exactly one append-only audit-log entry
per action, each capturing actor, action, target, before, and after.

Each privileged action is modelled as either a direct :func:`audit.write_audit`
call or a :func:`verification.transition` over a generated *valid* state
transition. Both ultimately append exactly one ``AuditLog`` row; the test runs a
generated sequence of N such actions against a single captured session and
asserts exactly N rows are appended — one per action — with the expected
actor/action/target/before/after fields.

Validates: Requirements 3.5, 7.9, 10.3, 11.7, 17.5, 22.2
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models.audit_log import AuditLog
from app.models.enums import VerificationState
from app.services import audit, verification


class _FakeSession:
    """Captured session counting add/flush calls (mirrors test_audit_service)."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed += 1


class _Entity:
    """Minimal verifiable entity carrying an id and a verification state."""

    def __init__(self, entity_id: UUID, state: VerificationState) -> None:
        self.id = entity_id
        self.verification_status = state


# Every permitted (current -> target) edge in the state machine. Used so the
# generated transitions are always legal and therefore each writes one row.
_VALID_TRANSITIONS = sorted(
    (
        (current.value, target.value)
        for current, targets in verification.ALLOWED_TRANSITIONS.items()
        for target in targets
    )
)

_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.text(max_size=12),
)
_json_dicts = st.one_of(
    st.none(),
    st.dictionaries(keys=st.text(min_size=1, max_size=8), values=_json_scalars, max_size=4),
)


@st.composite
def _write_audit_action(draw: st.DrawFn) -> dict:
    """A direct write_audit privileged action with an actor or a system label."""
    use_user_actor = draw(st.booleans())
    actor_id = uuid4() if use_user_actor else None
    actor_label = None if use_user_actor else draw(st.text(min_size=1, max_size=16))
    return {
        "kind": "write_audit",
        "actor_id": actor_id,
        "actor_label": actor_label,
        "action": draw(st.text(min_size=1, max_size=24)),
        "target_type": draw(st.text(min_size=1, max_size=24)),
        "target_id": draw(st.uuids()),
        "before": draw(_json_dicts),
        "after": draw(_json_dicts),
    }


@st.composite
def _transition_action(draw: st.DrawFn) -> dict:
    """A verification.transition privileged action over a valid state edge."""
    current_value, target_value = draw(st.sampled_from(_VALID_TRANSITIONS))
    reason = draw(st.one_of(st.none(), st.text(min_size=1, max_size=24)))
    return {
        "kind": "transition",
        "actor_id": uuid4(),
        "entity_id": draw(st.uuids()),
        "current": VerificationState(current_value),
        "target": VerificationState(target_value),
        "reason": reason,
    }


_actions = st.lists(
    st.one_of(_write_audit_action(), _transition_action()),
    min_size=0,
    max_size=12,
)


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(actions=_actions)
def test_each_privileged_action_writes_exactly_one_audit_entry(actions: list[dict]) -> None:
    db = _FakeSession()
    expected: list[dict] = []

    for spec in actions:
        if spec["kind"] == "write_audit":
            actor = SimpleNamespace(id=spec["actor_id"]) if spec["actor_id"] is not None else None
            audit.write_audit(
                db,
                actor=actor,
                action=spec["action"],
                target_type=spec["target_type"],
                target_id=spec["target_id"],
                before=spec["before"],
                after=spec["after"],
                actor_label=spec["actor_label"],
            )
            expected.append(
                {
                    "actor_id": spec["actor_id"],
                    "actor_label": spec["actor_label"],
                    "action": spec["action"],
                    "target_type": spec["target_type"],
                    "target_id": spec["target_id"],
                    "before": spec["before"],
                    "after": spec["after"],
                }
            )
        else:  # transition
            entity = _Entity(spec["entity_id"], spec["current"])
            actor = SimpleNamespace(id=spec["actor_id"])
            verification.transition(
                db,
                entity=entity,
                target_state=spec["target"],
                actor=actor,
                reason=spec["reason"],
            )
            after = {"verification_status": spec["target"].value}
            if spec["reason"] is not None:
                after["reason"] = spec["reason"]
            expected.append(
                {
                    "actor_id": spec["actor_id"],
                    "actor_label": None,
                    "action": "verification.transition",
                    "target_type": "_Entity",
                    "target_id": spec["entity_id"],
                    "before": {"verification_status": spec["current"].value},
                    "after": after,
                }
            )

    # Exactly one AuditLog row per action — no more, no fewer.
    rows = [obj for obj in db.added if isinstance(obj, AuditLog)]
    assert len(db.added) == len(rows) == len(actions)
    assert db.flushed == len(actions)

    # Each appended row captures actor, action, target, before, and after.
    for row, exp in zip(rows, expected):
        assert row.actor_id == exp["actor_id"]
        assert row.actor_label == exp["actor_label"]
        assert row.action == exp["action"]
        assert row.target_type == exp["target_type"]
        assert row.target_id == exp["target_id"]
        assert row.before == exp["before"]
        assert row.after == exp["after"]
