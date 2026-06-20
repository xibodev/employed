"""Response schemas for the versioned Export API (R21).

The Export API returns major entities rendered into open interchange schemas
(JSON Resume for candidates, schema.org ``JobPosting`` JSON-LD for jobs, a
normalized Application object). Those documents are open-ended standard
structures, so each export response is modeled as a free-form JSON object
rather than a fixed field set; the concrete shape is owned by the mappers in
``app/services/export.py``.
"""

from __future__ import annotations

from typing import Any

from pydantic import RootModel


class ExportDocument(RootModel[dict[str, Any]]):
    """A single export document in a standard interchange schema (R21.2).

    Wraps the raw mapper output (JSON Resume / JobPosting JSON-LD / normalized
    Application) so the Export API advertises a JSON-object response in its
    OpenAPI schema while leaving the standard document structure untouched.
    """

    root: dict[str, Any]
