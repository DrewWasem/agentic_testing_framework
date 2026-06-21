"""Reporting — turn a :class:`Verdict` into an auditable artifact.

Two renderers, both **standard-library only** (no jinja2, no lxml): a self-contained HTML
report of the full evidence ledger, and a JUnit XML file a CI runner can consume. The
top-level package re-exports :func:`render_html` and :func:`render_junit`.
"""

from __future__ import annotations

from .html import render_html
from .junit import render_junit

__all__ = ["render_html", "render_junit"]
