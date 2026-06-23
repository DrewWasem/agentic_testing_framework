"""Reporting — turn a :class:`Verdict` into an auditable artifact.

Three renderers, all **standard-library only** (no jinja2, no lxml): a self-contained HTML
report of one verdict's full evidence ledger, a browsable HTML page for a whole *suite* of
verdicts, and a JUnit XML file a CI runner can consume. The top-level package re-exports
:func:`render_html`, :func:`render_suite_html`, and :func:`render_junit`.
"""

from __future__ import annotations

from .html import render_html
from .junit import render_junit
from .suite import render_suite_html

__all__ = ["render_html", "render_junit", "render_suite_html"]
