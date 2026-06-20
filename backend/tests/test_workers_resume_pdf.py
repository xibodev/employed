from __future__ import annotations

import asyncio
from contextlib import contextmanager

import pytest

from app.services.resume_templates import ProfileVersionNotFoundError


class _FakeProfileVersion:
    """Minimal ProfileVersion stand-in carrying a JSON Resume document.

    ``to_json_resume`` reads the ``json_resume`` attribute, so a duck-typed
    object is enough to exercise the worker end-to-end without a DB table.
    """

    def __init__(self, version_id: str, json_resume: dict) -> None:
        self.id = version_id
        self.json_resume = json_resume


class _FakeVersionSession:
    """Fake worker DB session whose ``get`` returns a preset version (or None)."""

    def __init__(self, version: _FakeProfileVersion | None) -> None:
        self._version = version

    def get(self, _model, _pk):
        return self._version

    def close(self) -> None:  # pragma: no cover - parity with real session
        pass


def _patch_worker_session(monkeypatch, version: _FakeProfileVersion | None) -> None:
    """Wire ``render_resume_pdf`` to a fake session, matching worker-test style."""
    from app.workers import tasks

    @contextmanager
    def fake_session_scope():
        yield _FakeVersionSession(version)

    monkeypatch.setattr(tasks, "session_scope", fake_session_scope)
    monkeypatch.setattr(tasks, "resolve_model", lambda name, aliases=None: _FakeProfileVersion)


_SAMPLE_RESUME = {
    "basics": {
        "name": "Ana Tembe",
        "label": "Backend Engineer",
        "email": "ana@example.com",
        "summary": "Builds reliable services.",
    },
    "work": [
        {
            "name": "Acme",
            "position": "Engineer",
            "startDate": "2021",
            "endDate": "2024",
            "highlights": ["Shipped the payments service"],
        }
    ],
    "skills": [{"name": "Python", "keywords": ["FastAPI", "SQLAlchemy"]}],
}


def test_render_resume_pdf_produces_downloadable_pdf(monkeypatch, tmp_path):
    """R14.2/R14.3: rendering a present ProfileVersion yields a downloadable PDF."""
    version = _FakeProfileVersion("11111111-1111-1111-1111-111111111111", _SAMPLE_RESUME)
    _patch_worker_session(monkeypatch, version)

    from app.workers import tasks

    artifact = asyncio.run(
        tasks.render_resume_pdf(
            {},
            version.id,
            template_id="modern",
            artifact_dir=str(tmp_path),
        )
    )

    # Download descriptor is well-formed and JSON-serialisable.
    assert artifact["profile_version_id"] == version.id
    assert artifact["template_id"] == "modern"
    assert artifact["content_type"] == "application/pdf"
    assert artifact["size_bytes"] > 0

    # The artifact is a real, downloadable PDF on disk under the temp dir.
    from pathlib import Path

    pdf_path = Path(artifact["artifact_path"])
    assert pdf_path.is_file()
    assert pdf_path.parent == tmp_path
    pdf_bytes = pdf_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) == artifact["size_bytes"]


def test_render_resume_pdf_missing_version_raises(monkeypatch, tmp_path):
    """R14.4: a missing ProfileVersion raises so the endpoint can return 404."""
    _patch_worker_session(monkeypatch, None)

    from app.workers import tasks

    with pytest.raises(ProfileVersionNotFoundError):
        asyncio.run(
            tasks.render_resume_pdf(
                {},
                "99999999-9999-9999-9999-999999999999",
                artifact_dir=str(tmp_path),
            )
        )

    # Nothing should have been written when the version is absent.
    assert not any(tmp_path.iterdir())
