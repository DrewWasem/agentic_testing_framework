"""Drive a command-line program as the agent under test (input on stdin, output on stdout)."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence


class CliTarget:
    def __init__(self, command: Sequence[str], *, timeout: float = 60.0, name: str = "cli") -> None:
        self.command = list(command)
        self.timeout = timeout
        self.name = name

    def run(self, input: str) -> str:
        result = subprocess.run(
            self.command,
            input=input,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"CLI target exited {result.returncode}: {result.stderr.strip()}")
        return result.stdout
