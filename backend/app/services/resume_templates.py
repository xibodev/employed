"""Predefined resume templates and server-side PDF rendering (R14).

This module backs the PDF resume export feature. It provides:

- :data:`RESUME_TEMPLATES` — a registry of predefined ``Resume_Template`` layouts
  (R14.1). Each template renders a JSON Resume document into an HTML document with
  its own typographic/colour treatment.
- :func:`render_resume_html` / :func:`render_resume_pdf_bytes` — server-side
  rendering of a chosen template to HTML and then to PDF bytes (R14.2).
- :func:`build_resume_artifact` — renders and persists a downloadable artifact,
  returning a serialisable reference (R14.3).

Dependency choice (flagged): no HTML→PDF library is pinned in any
``requirements*.txt``. Rather than adding an unpinned native dependency
(``weasyprint``/``xhtml2pdf`` pull in heavy system libraries), rendering is kept
behind the :func:`_html_to_pdf` abstraction: it will transparently use
``weasyprint`` or ``xhtml2pdf`` *if* they are installed, and otherwise falls back
to a small, self-contained PDF writer that emits a valid, downloadable
single-font PDF. When a richer PDF engine is desired, pin it in
``requirements-api.txt`` and :func:`_html_to_pdf` will pick it up with no other
changes.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DEFAULT_RESUME_TEMPLATE_ID = "classic"


class ResumeTemplateNotFoundError(KeyError):
    """Raised when a requested resume template id is not registered."""


class ProfileVersionNotFoundError(LookupError):
    """Raised when the requested ProfileVersion does not exist (R14.4).

    The calling endpoint maps this to an HTTP ``404`` not-found response.
    """


@dataclass(frozen=True)
class ResumeTemplate:
    """A predefined resume layout (R14.1).

    ``accent_color`` and ``font_family`` drive the template's visual treatment;
    ``render`` produces a full HTML document from a JSON Resume mapping.
    """

    id: str
    name: str
    description: str
    accent_color: str
    font_family: str
    render: Callable[[dict[str, Any]], str]


# --------------------------------------------------------------------------- #
# JSON Resume → HTML helpers
# --------------------------------------------------------------------------- #


def _esc(value: Any) -> str:
    """HTML-escape a value, rendering ``None`` as an empty string."""
    if value is None:
        return ""
    return _html.escape(str(value))


def _date_range(start: Any, end: Any) -> str:
    start_s = _esc(start)
    end_s = _esc(end) or "Present"
    if not start_s and not end_s:
        return ""
    if not start_s:
        return end_s
    return f"{start_s} – {end_s}"


def _basics_block(basics: dict[str, Any]) -> str:
    name = _esc(basics.get("name"))
    label = _esc(basics.get("label"))
    summary = _esc(basics.get("summary"))

    contacts: list[str] = []
    for key in ("email", "phone", "url"):
        value = basics.get(key)
        if value:
            contacts.append(_esc(value))
    location = basics.get("location")
    if isinstance(location, dict):
        loc_parts = [location.get("address"), location.get("city"), location.get("region"), location.get("countryCode")]
        loc = ", ".join(_esc(part) for part in loc_parts if part)
        if loc:
            contacts.append(loc)
    elif location:
        contacts.append(_esc(location))

    profiles = basics.get("profiles")
    if isinstance(profiles, list):
        for profile in profiles:
            if isinstance(profile, dict) and profile.get("url"):
                network = _esc(profile.get("network")) or "Profile"
                contacts.append(f"{network}: {_esc(profile.get('url'))}")

    parts = ['<header class="resume-header">']
    if name:
        parts.append(f"<h1>{name}</h1>")
    if label:
        parts.append(f'<p class="label">{label}</p>')
    if contacts:
        parts.append(f'<p class="contacts">{" · ".join(contacts)}</p>')
    if summary:
        parts.append(f'<p class="summary">{summary}</p>')
    parts.append("</header>")
    return "".join(parts)


def _highlights(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return ""
    lis = "".join(f"<li>{_esc(item)}</li>" for item in items if item)
    return f"<ul>{lis}</ul>" if lis else ""


def _section(title: str, body: str) -> str:
    if not body:
        return ""
    return f'<section class="resume-section"><h2>{_esc(title)}</h2>{body}</section>'


def _work_block(work: Any) -> str:
    if not isinstance(work, list):
        return ""
    entries: list[str] = []
    for item in work:
        if not isinstance(item, dict):
            continue
        org = _esc(item.get("name") or item.get("company"))
        position = _esc(item.get("position"))
        dates = _date_range(item.get("startDate"), item.get("endDate"))
        summary = _esc(item.get("summary"))
        heading = " — ".join(part for part in (position, org) if part)
        block = ['<div class="entry">']
        if heading:
            block.append(f'<p class="entry-title">{heading}</p>')
        if dates:
            block.append(f'<p class="entry-meta">{dates}</p>')
        if summary:
            block.append(f"<p>{summary}</p>")
        block.append(_highlights(item.get("highlights")))
        block.append("</div>")
        entries.append("".join(block))
    return _section("Experience", "".join(entries))


def _education_block(education: Any) -> str:
    if not isinstance(education, list):
        return ""
    entries: list[str] = []
    for item in education:
        if not isinstance(item, dict):
            continue
        institution = _esc(item.get("institution"))
        study = " ".join(part for part in (_esc(item.get("studyType")), _esc(item.get("area"))) if part)
        dates = _date_range(item.get("startDate"), item.get("endDate"))
        heading = " — ".join(part for part in (study, institution) if part)
        block = ['<div class="entry">']
        if heading:
            block.append(f'<p class="entry-title">{heading}</p>')
        if dates:
            block.append(f'<p class="entry-meta">{dates}</p>')
        block.append("</div>")
        entries.append("".join(block))
    return _section("Education", "".join(entries))


def _skills_block(skills: Any) -> str:
    if not isinstance(skills, list):
        return ""
    items: list[str] = []
    for skill in skills:
        if not isinstance(skill, dict):
            continue
        name = _esc(skill.get("name"))
        keywords = skill.get("keywords")
        if isinstance(keywords, list) and keywords:
            kw = ", ".join(_esc(k) for k in keywords if k)
            items.append(f"<li>{name}: {kw}</li>" if name else f"<li>{kw}</li>")
        elif name:
            items.append(f"<li>{name}</li>")
    return _section("Skills", f"<ul>{''.join(items)}</ul>" if items else "")


def _projects_block(projects: Any) -> str:
    if not isinstance(projects, list):
        return ""
    entries: list[str] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        name = _esc(item.get("name"))
        description = _esc(item.get("description"))
        block = ['<div class="entry">']
        if name:
            block.append(f'<p class="entry-title">{name}</p>')
        if description:
            block.append(f"<p>{description}</p>")
        block.append(_highlights(item.get("highlights")))
        block.append("</div>")
        entries.append("".join(block))
    return _section("Projects", "".join(entries))


def _body_sections(resume: dict[str, Any]) -> str:
    return "".join(
        (
            _work_block(resume.get("work")),
            _education_block(resume.get("education")),
            _skills_block(resume.get("skills")),
            _projects_block(resume.get("projects")),
        )
    )


def _document(resume: dict[str, Any], *, template: ResumeTemplate) -> str:
    basics = resume.get("basics")
    basics = basics if isinstance(basics, dict) else {}
    title = _esc(basics.get("name")) or "Resume"
    css = f"""
      body {{ font-family: {template.font_family}; color: #1a1a1a; margin: 0; padding: 40px; }}
      h1 {{ color: {template.accent_color}; margin: 0 0 4px; font-size: 26px; }}
      h2 {{ color: {template.accent_color}; border-bottom: 2px solid {template.accent_color};
            font-size: 15px; text-transform: uppercase; letter-spacing: 1px; margin: 22px 0 8px; }}
      .label {{ font-size: 14px; color: #444; margin: 0 0 6px; }}
      .contacts {{ font-size: 11px; color: #555; margin: 0 0 10px; }}
      .summary {{ font-size: 12px; }}
      .entry {{ margin-bottom: 12px; }}
      .entry-title {{ font-weight: bold; margin: 0; font-size: 13px; }}
      .entry-meta {{ color: #666; font-size: 11px; margin: 0 0 4px; }}
      ul {{ margin: 4px 0 0 18px; padding: 0; font-size: 12px; }}
    """
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<title>{title}</title><style>{css}</style></head><body>"
        f"{_basics_block(basics)}{_body_sections(resume)}"
        "</body></html>"
    )


# --------------------------------------------------------------------------- #
# Template registry (R14.1)
# --------------------------------------------------------------------------- #

_TEMPLATE_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "classic",
        "Classic",
        "Serif, single-column, conservative layout.",
        "#1f2d3d",
        "Georgia, 'Times New Roman', serif",
    ),
    ("modern", "Modern", "Sans-serif with a coloured accent.", "#2563eb", "'Helvetica Neue', Arial, sans-serif"),
    ("minimal", "Minimal", "Restrained monochrome layout.", "#111111", "Arial, sans-serif"),
)


def _make_template(spec: tuple[str, str, str, str, str]) -> ResumeTemplate:
    template_id, name, description, accent, font = spec
    template = ResumeTemplate(
        id=template_id,
        name=name,
        description=description,
        accent_color=accent,
        font_family=font,
        render=lambda resume: "",  # replaced below once the instance exists
    )
    # Bind the renderer to the concrete template (accent/font) now that it exists.
    object.__setattr__(template, "render", lambda resume, _t=template: _document(resume, template=_t))
    return template


RESUME_TEMPLATES: dict[str, ResumeTemplate] = {spec[0]: _make_template(spec) for spec in _TEMPLATE_SPECS}


def list_resume_templates() -> list[dict[str, str]]:
    """Return public metadata for every predefined template (R14.1)."""
    return [{"id": t.id, "name": t.name, "description": t.description} for t in RESUME_TEMPLATES.values()]


def get_resume_template(template_id: str | None) -> ResumeTemplate:
    """Resolve a template by id, falling back to the default when ``None``.

    Raises :class:`ResumeTemplateNotFoundError` for an unknown, non-empty id.
    """
    key = template_id or DEFAULT_RESUME_TEMPLATE_ID
    try:
        return RESUME_TEMPLATES[key]
    except KeyError as exc:
        raise ResumeTemplateNotFoundError(key) from exc


def render_resume_html(json_resume: dict[str, Any], template_id: str | None = None) -> str:
    """Render a JSON Resume document to a full HTML document (R14.2)."""
    template = get_resume_template(template_id)
    return template.render(json_resume or {})


# --------------------------------------------------------------------------- #
# HTML → PDF abstraction (dependency choice flagged in the module docstring)
# --------------------------------------------------------------------------- #

_BLOCK_CLOSE_RE = re.compile(r"</(?:h[1-6]|p|li|div|section|header|ul)>", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_LI_OPEN_RE = re.compile(r"<li[^>]*>", re.IGNORECASE)


def _html_to_text_lines(doc: str) -> list[str]:
    """Flatten an HTML document into plain text lines for the fallback writer."""
    text = doc
    text = re.sub(r"(?is)<style.*?</style>", "", text)
    text = re.sub(r"(?is)<head.*?</head>", "", text)
    text = _LI_OPEN_RE.sub("• ", text)
    text = _BR_RE.sub("\n", text)
    text = _BLOCK_CLOSE_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = _html.unescape(text)

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    # Collapse runs of blank lines into a single separator.
    result: list[str] = []
    for line in lines:
        if line or (result and result[-1] != ""):
            result.append(line)
    while result and result[-1] == "":
        result.pop()
    return result


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(line: str, width: int = 95) -> list[str]:
    if line == "":
        return [""]
    chunks: list[str] = []
    while len(line) > width:
        chunks.append(line[:width])
        line = line[width:]
    chunks.append(line)
    return chunks


def _content_stream(lines: list[str]) -> bytes:
    cmds = ["BT", "/F1 11 Tf", "72 720 Td", "15 TL"]
    for index, line in enumerate(lines):
        if index > 0:
            cmds.append("T*")
        cmds.append(f"({_pdf_escape(line)}) Tj")
    cmds.append("ET")
    return ("\n".join(cmds)).encode("latin-1", "replace")


def _assemble_pdf(objects: dict[int, bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    max_num = max(objects)
    for num in range(1, max_num + 1):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode("latin-1")
        out += objects[num]
        out += b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {max_num + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for num in range(1, max_num + 1):
        out += f"{offsets[num]:010d} 00000 n \n".encode("latin-1")
    out += b"trailer\n"
    out += f"<< /Size {max_num + 1} /Root 1 0 R >>\n".encode("latin-1")
    out += f"startxref\n{xref_offset}\n".encode("latin-1")
    out += b"%%EOF\n"
    return bytes(out)


def _fallback_text_pdf(doc: str, *, lines_per_page: int = 44) -> bytes:
    """Render text extracted from *doc* into a valid multi-page PDF."""
    wrapped: list[str] = []
    for line in _html_to_text_lines(doc) or [""]:
        wrapped.extend(_wrap(line))

    pages = [wrapped[i : i + lines_per_page] for i in range(0, len(wrapped), lines_per_page)] or [[""]]

    objects: dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"

    page_numbers: list[int] = []
    next_num = 4
    for page_lines in pages:
        page_num = next_num
        content_num = next_num + 1
        next_num += 2
        page_numbers.append(page_num)
        objects[page_num] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents " + f"{content_num} 0 R >>".encode("latin-1")
        )
        stream = _content_stream(page_lines)
        objects[content_num] = (
            b"<< /Length " + str(len(stream)).encode("latin-1") + b" >>\nstream\n" + stream + b"\nendstream"
        )

    kids = " ".join(f"{num} 0 R" for num in page_numbers)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_numbers)} >>".encode("latin-1")
    return _assemble_pdf(objects)


def _html_to_pdf(doc: str) -> bytes:
    """Convert an HTML document to PDF bytes (R14.2).

    Uses an installed engine when available and otherwise falls back to the
    self-contained text PDF writer. See the module docstring for the rationale.
    """
    try:
        import weasyprint  # type: ignore

        return weasyprint.HTML(string=doc).write_pdf()
    except Exception:
        pass

    try:
        from io import BytesIO

        from xhtml2pdf import pisa  # type: ignore

        buffer = BytesIO()
        result = pisa.CreatePDF(src=doc, dest=buffer)
        if not result.err:
            return buffer.getvalue()
    except Exception:
        pass

    return _fallback_text_pdf(doc)


def render_resume_pdf_bytes(json_resume: dict[str, Any], template_id: str | None = None) -> bytes:
    """Render a JSON Resume document to PDF bytes via a chosen template (R14.2)."""
    return _html_to_pdf(render_resume_html(json_resume, template_id))


# --------------------------------------------------------------------------- #
# Downloadable artifact (R14.3)
# --------------------------------------------------------------------------- #


def default_artifact_dir() -> Path:
    """Default directory for rendered resume artifacts.

    Honours the optional ``RESUME_ARTIFACT_DIR`` environment variable, falling
    back to a stable subdirectory of the system temp dir so the worker is
    functional without any extra configuration.
    """
    import os
    import tempfile

    configured = os.environ.get("RESUME_ARTIFACT_DIR")
    base = Path(configured) if configured else Path(tempfile.gettempdir()) / "employed-resume-artifacts"
    return base


def build_resume_artifact(
    json_resume: dict[str, Any],
    *,
    template_id: str | None,
    profile_version_id: str,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Render and persist a downloadable PDF artifact, returning its reference (R14.3).

    The returned mapping is JSON-serialisable so it can travel back through the
    arq result backend and be handed to an endpoint as a download descriptor.

    Storage selection:
    - When an explicit ``artifact_dir`` is given, the PDF is written there (used
      by tests and any caller that wants a specific local path).
    - Otherwise, when R2/S3 resume storage is configured, the PDF is uploaded to
      durable object storage (survives EC2 restarts) and the reference carries
      ``storage="r2"`` + ``bucket`` + ``key``.
    - Otherwise it falls back to the local default directory (dev/test/CI).
    """
    from app.services import resume_storage

    template = get_resume_template(template_id)
    pdf_bytes = render_resume_pdf_bytes(json_resume, template.id)
    filename = f"resume-{profile_version_id}-{template.id}.pdf"

    reference: dict[str, Any] = {
        "profile_version_id": str(profile_version_id),
        "template_id": template.id,
        "filename": filename,
        "content_type": "application/pdf",
        "size_bytes": len(pdf_bytes),
        "rendered_at": datetime.now(timezone.utc).isoformat(),
    }

    if artifact_dir is None and resume_storage.is_configured():
        key = resume_storage.object_key(str(profile_version_id), filename)
        upload = resume_storage.upload_pdf(pdf_bytes, key=key, content_type="application/pdf")
        reference.update({"storage": upload["storage"], "bucket": upload["bucket"], "key": upload["key"]})
        return reference

    directory = Path(artifact_dir) if artifact_dir is not None else default_artifact_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(pdf_bytes)
    reference.update({"storage": "local", "artifact_path": str(path)})
    return reference
