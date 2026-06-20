"""The core promise: importing the package pulls in zero third-party dependencies.

Rather than a hand-maintained block-list of SDK names, this asserts that importing the
package adds only standard-library modules (plus the package itself) to a clean
interpreter — so ANY accidental third-party import is caught, not just a known few.
"""

import subprocess
import sys

_PROBE = """
import sys
before = set(sys.modules)
import agentic_testing_framework
added = set(sys.modules) - before
stdlib = sys.stdlib_module_names
foreign = sorted(
    m for m in added
    if not m.startswith("agentic_testing_framework")
    and m.split(".")[0] not in stdlib
    and not m.startswith("_")
)
print("OK" if not foreign else "FOREIGN:" + ",".join(foreign))
"""


def test_core_import_adds_only_stdlib_modules():
    result = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK", result.stdout
