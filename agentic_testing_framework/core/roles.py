"""Role tags embedded in every system prompt.

A tiny, dependency-free module so both the providers layer (the offline mock keys its
canned responses off the role) and the tribunal layer can share the same constants
without an import cycle.
"""

from __future__ import annotations

import re

ROLE_REVIEWER = "reviewer"
ROLE_COUNCIL = "council"
ROLE_ORCHESTRATOR = "orchestrator"
ROLE_GENERATOR = "generator"
ROLE_METRIC = "metric"

_ROLE_RE = re.compile(r"atf-role=(\w+)")


def role_header(role: str, extra: str = "") -> str:
    """Build the machine-readable header line prepended to a stage's system prompt."""

    suffix = f" {extra}" if extra else ""
    return f"[atf-role={role}{suffix}]"


def detect_role(system: str) -> str:
    """Recover the role tag from a system prompt (used by the offline mock)."""

    match = _ROLE_RE.search(system)
    return match.group(1) if match else ""
