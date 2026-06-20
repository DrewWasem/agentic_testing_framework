"""Drive an HTTP endpoint as the agent under test (standard-library urllib only)."""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from urllib.parse import urlparse


def _is_private_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


class HttpTarget:
    """POST ``{input_field: input}`` as JSON and read ``output_field`` from the JSON reply.

    Falls back to returning the raw response body if it isn't JSON or lacks the field.
    HTTP and network errors become a clean ``RuntimeError`` rather than crashing the case.

    ``block_private_hosts`` is an opt-in SSRF guard. It defaults to **False** because
    pointing a test harness at a localhost or private-network agent is a normal, expected
    use. Enable it when the target URL might be influenced by untrusted input. ``resolver``
    is injectable so the guard is testable offline.
    """

    def __init__(
        self,
        url: str,
        *,
        method: str = "POST",
        headers: Mapping[str, str] | None = None,
        input_field: str = "input",
        output_field: str = "output",
        timeout: float = 30.0,
        block_private_hosts: bool = False,
        resolver: Callable[[str], list[str]] | None = None,
        name: str = "http",
    ) -> None:
        self.url = url
        self.method = method
        self.headers = dict(headers) if headers else {}
        self.input_field = input_field
        self.output_field = output_field
        self.timeout = timeout
        self.block_private_hosts = block_private_hosts
        self._resolver = resolver
        self.name = name

    def run(self, input: str) -> str:
        if self.block_private_hosts:
            self._guard_host()
        payload = json.dumps({self.input_field: input}).encode("utf-8")
        headers = {"Content-Type": "application/json", **self.headers}
        request = urllib.request.Request(
            self.url, data=payload, method=self.method, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP target {self.url} returned {exc.code} {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"HTTP target {self.url} unreachable: {exc.reason}") from exc
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body
        if isinstance(data, dict) and self.output_field in data:
            return str(data[self.output_field])
        return body

    def _guard_host(self) -> None:
        host = (urlparse(self.url).hostname or "").lower()
        if not host:
            raise RuntimeError(f"HTTP target has no host to validate: {self.url!r}")
        if _is_private_ip(host):
            raise RuntimeError(f"Blocked request to private address: {host}")
        # Catch obfuscated IPv4 literals (octal/decimal/hex) that ``ipaddress`` rejects but
        # the OS resolver accepts, e.g. "0177.0.0.1" or "2130706433" -> 127.0.0.1.
        try:
            canonical: str | None = socket.inet_ntoa(socket.inet_aton(host))
        except OSError:
            canonical = None
        if canonical is not None and _is_private_ip(canonical):
            raise RuntimeError(f"Blocked request to private address: {host} ({canonical})")
        if host == "localhost" or host.endswith(".local"):
            raise RuntimeError(f"Blocked request to local host: {host}")
        if canonical is not None:
            return  # a public IPv4 literal — name resolution below would just echo it
        try:
            resolved = self._resolver(host) if self._resolver else self._resolve(host)
        except OSError as exc:
            raise RuntimeError(f"Could not resolve host {host!r}: {exc}") from exc
        private = [ip for ip in resolved if _is_private_ip(ip)]
        if private:
            raise RuntimeError(
                f"Blocked: {host} resolves to private address(es): {', '.join(private)}"
            )

    @staticmethod
    def _resolve(host: str) -> list[str]:
        return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]
