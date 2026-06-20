from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.profile_version import ProfileVersion
from app.services import profiles_versioning as pv


class _FakeQuery:
    def __init__(self, max_version: int | None) -> None:
        self._max = max_version

    def filter(self, *args: object, **kwargs: object) -> "_FakeQuery":
        return self

    def scalar(self) -> int | None:
        return self._max


class _FakeSession:
    """Minimal Session stand-in for save_version's add/flush/query(max) usage."""

    def __init__(self, existing_max: int | None = None) -> None:
        self.added: list[object] = []
        self.flushed = 0
        self._existing_max = existing_max

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed += 1

    def query(self, *args: object) -> _FakeQuery:
        return _FakeQuery(self._existing_max)


def test_empty_json_resume_is_valid() -> None:
    assert pv.validate_json_resume(pv.empty_json_resume()) == {"basics": {}}


def test_validate_json_resume_accepts_known_sections() -> None:
    document = {
        "basics": {"name": "Ada", "profiles": [], "location": {"city": "Maputo"}},
        "work": [{"name": "Acme"}],
        "skills": [],
        "meta": {"version": "v1.0.0"},
    }
    assert pv.validate_json_resume(document) is document


@pytest.mark.parametrize(
    "document",
    [
        "not-an-object",
        ["array"],
        {"basics": ["should-be-object"]},
        {"work": {"should-be": "array"}},
        {"basics": {"profiles": {"should-be": "array"}}},
        {"basics": {"location": ["should-be-object"]}},
    ],
)
def test_validate_json_resume_rejects_bad_shapes(document: object) -> None:
    with pytest.raises(pv.JSONResumeValidationError):
        pv.validate_json_resume(document)


def test_save_version_assigns_monotonic_number_and_snapshots() -> None:
    db = _FakeSession(existing_max=2)
    user_id = uuid4()
    profile = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        json_resume={"basics": {"name": "Ada"}},
    )

    version = pv.save_version(db, profile=profile)

    assert isinstance(version, ProfileVersion)
    assert version.version_number == 3
    assert version.profile_id == profile.id
    assert version.user_id == user_id
    assert version.json_resume == {"basics": {"name": "Ada"}}
    assert db.added == [version]
    assert db.flushed == 1


def test_save_version_snapshot_is_independent_of_later_edits() -> None:
    db = _FakeSession(existing_max=None)
    profile = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        json_resume={"basics": {"name": "Ada"}},
    )

    version = pv.save_version(db, profile=profile)
    assert version.version_number == 1

    # Mutating the live working copy must not change the captured snapshot.
    profile.json_resume["basics"]["name"] = "Grace"
    assert version.json_resume == {"basics": {"name": "Ada"}}


def test_save_version_updates_working_copy_when_resume_supplied() -> None:
    db = _FakeSession(existing_max=None)
    profile = SimpleNamespace(id=uuid4(), user_id=uuid4(), json_resume=None)

    new_resume = {"basics": {"name": "Ada"}, "skills": []}
    version = pv.save_version(db, profile=profile, json_resume=new_resume)

    assert profile.json_resume == new_resume
    assert version.json_resume == new_resume


def test_save_version_rejects_invalid_resume() -> None:
    db = _FakeSession()
    profile = SimpleNamespace(id=uuid4(), user_id=uuid4(), json_resume=None)

    with pytest.raises(pv.JSONResumeValidationError):
        pv.save_version(db, profile=profile, json_resume={"work": {"bad": "shape"}})
