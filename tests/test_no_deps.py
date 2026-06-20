"""The core promise: importing the package pulls in zero third-party dependencies."""

import subprocess
import sys


def test_core_import_pulls_no_third_party():
    code = (
        "import sys, agentic_testing_framework;"
        "sdks=('anthropic','openai','requests','httpx','pydantic','numpy','aiohttp');"
        "loaded=[m for m in sdks if m in sys.modules];"
        "print('OK' if not loaded else 'BAD:' + ','.join(loaded))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK", result.stdout
