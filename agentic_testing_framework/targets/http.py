"""Drive an HTTP endpoint as the agent under test (standard-library urllib only)."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping


class HttpTarget:
    """POST ``{input_field: input}`` as JSON and read ``output_field`` from the JSON reply.

    Falls back to returning the raw response body if it isn't JSON or lacks the field.
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
        name: str = "http",
    ) -> None:
        self.url = url
        self.method = method
        self.headers = dict(headers) if headers else {}
        self.input_field = input_field
        self.output_field = output_field
        self.timeout = timeout
        self.name = name

    def run(self, input: str) -> str:
        payload = json.dumps({self.input_field: input}).encode("utf-8")
        headers = {"Content-Type": "application/json", **self.headers}
        request = urllib.request.Request(
            self.url, data=payload, method=self.method, headers=headers
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body
        if isinstance(data, dict) and self.output_field in data:
            return str(data[self.output_field])
        return body
