"""A provider that shells out to the Claude CLI (``claude -p``).

This matches the convention used across the surrounding ecosystem: reach the model through
the already-authenticated CLI rather than an SDK. It needs no API key in code and adds no
dependency (``subprocess`` is standard library), so the core stays dependency-free. The
subprocess call is injectable via ``runner`` so tests stay fully offline.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence


class ClaudeCLIProvider:
    """Reach a model via ``claude -p --output-format text`` (prompt piped on stdin).

    The recommended real backend in a Claude-CLI ecosystem. Keep the ``MockProvider`` as
    the test/offline default; inject ``runner`` to exercise this provider without a CLI.
    """

    name = "claude-cli"

    def __init__(
        self,
        *,
        model: str | None = None,
        command: str = "claude",
        extra_args: Sequence[str] = (),
        timeout: float = 120.0,
        runner: Callable[[str], str] | None = None,
    ) -> None:
        self.model = model
        self.command = command
        self.extra_args = tuple(extra_args)
        self.timeout = timeout
        self._runner = runner or self._run_subprocess

    def complete(self, system: str, prompt: str) -> str:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        return self._runner(full_prompt)

    def _run_subprocess(self, full_prompt: str) -> str:
        cmd = [self.command, "-p", "--output-format", "text"]
        if self.model:
            cmd += ["--model", self.model]
        cmd += list(self.extra_args)
        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI exited {result.returncode}: {result.stderr.strip()}")
        return result.stdout
