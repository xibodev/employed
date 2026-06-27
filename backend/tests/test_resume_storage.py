from __future__ import annotations

from app.services import resume_storage, resume_templates

_JSON_RESUME = {"basics": {"name": "Ada Lovelace", "label": "Engineer"}}


def _clear_storage_settings(monkeypatch) -> None:
    monkeypatch.setattr(resume_storage.settings, "resume_storage_backend", "local", raising=False)
    monkeypatch.setattr(resume_storage.settings, "resume_s3_bucket", None, raising=False)
    monkeypatch.setattr(resume_storage.settings, "resume_s3_endpoint_url", None, raising=False)
    monkeypatch.setattr(resume_storage.settings, "resume_s3_access_key_id", None, raising=False)
    monkeypatch.setattr(resume_storage.settings, "resume_s3_secret_access_key", None, raising=False)


def _set_storage_settings(monkeypatch) -> None:
    monkeypatch.setattr(resume_storage.settings, "resume_storage_backend", "r2", raising=False)
    monkeypatch.setattr(resume_storage.settings, "resume_s3_bucket", "employed-prod-resumes", raising=False)
    monkeypatch.setattr(
        resume_storage.settings, "resume_s3_endpoint_url", "https://acct.r2.cloudflarestorage.com", raising=False
    )
    monkeypatch.setattr(resume_storage.settings, "resume_s3_access_key_id", "akid", raising=False)
    monkeypatch.setattr(resume_storage.settings, "resume_s3_secret_access_key", "secret", raising=False)


def test_is_configured_false_when_backend_local(monkeypatch):
    _clear_storage_settings(monkeypatch)
    assert resume_storage.is_configured() is False


def test_is_configured_false_when_backend_r2_but_incomplete(monkeypatch):
    _set_storage_settings(monkeypatch)
    monkeypatch.setattr(resume_storage.settings, "resume_s3_bucket", None, raising=False)
    assert resume_storage.is_configured() is False


def test_is_configured_true_when_fully_set(monkeypatch):
    _set_storage_settings(monkeypatch)
    assert resume_storage.is_configured() is True


def test_object_key_is_stable_and_namespaced():
    key = resume_storage.object_key("pv-123", "resume-pv-123-classic.pdf")
    assert key == "resumes/pv-123/resume-pv-123-classic.pdf"


def test_build_resume_artifact_local_fallback(monkeypatch, tmp_path):
    _clear_storage_settings(monkeypatch)
    artifact = resume_templates.build_resume_artifact(
        _JSON_RESUME, template_id=None, profile_version_id="pv-1", artifact_dir=str(tmp_path)
    )
    assert artifact["storage"] == "local"
    assert artifact["artifact_path"].endswith(".pdf")
    assert artifact["size_bytes"] > 0


def test_build_resume_artifact_uploads_to_r2_when_configured(monkeypatch):
    _set_storage_settings(monkeypatch)
    captured = {}

    def _fake_upload(pdf_bytes, *, key, content_type="application/pdf"):
        captured["key"] = key
        captured["size"] = len(pdf_bytes)
        captured["content_type"] = content_type
        return {"storage": "r2", "bucket": "employed-prod-resumes", "key": key}

    monkeypatch.setattr(resume_storage, "upload_pdf", _fake_upload)

    artifact = resume_templates.build_resume_artifact(_JSON_RESUME, template_id=None, profile_version_id="pv-9")

    assert artifact["storage"] == "r2"
    assert artifact["bucket"] == "employed-prod-resumes"
    assert artifact["key"] == "resumes/pv-9/resume-pv-9-classic.pdf"
    assert "artifact_path" not in artifact
    assert captured["size"] == artifact["size_bytes"] > 0
    assert captured["content_type"] == "application/pdf"


def test_explicit_artifact_dir_forces_local_even_when_r2_configured(monkeypatch, tmp_path):
    _set_storage_settings(monkeypatch)

    def _boom(*_args, **_kwargs):  # pragma: no cover - must not be called
        raise AssertionError("R2 upload must not run when an explicit artifact_dir is given")

    monkeypatch.setattr(resume_storage, "upload_pdf", _boom)

    artifact = resume_templates.build_resume_artifact(
        _JSON_RESUME, template_id=None, profile_version_id="pv-2", artifact_dir=str(tmp_path)
    )
    assert artifact["storage"] == "local"
    assert artifact["artifact_path"].endswith(".pdf")
