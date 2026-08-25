"""The HTTP plumbing, kept apart from the API surface.

Everything in this file is about *how* a request is made — auth header, JSON
encoding, turning a failure into the right exception. Nothing in it knows what
any particular endpoint does. That separation is what keeps `client.py` and
`session.py` readable: they describe the API, this describes the wire.
"""

from __future__ import annotations

import json as _json
from collections.abc import Iterator
from typing import Any

import httpx

from . import errors

#: Where the hosted service lives. Override for a self-hosted instance.
DEFAULT_BASE_URL = "https://darkerapi.com/api/v1"

#: Long enough for a Steam login (`sessions.create` genuinely takes a while),
#: short enough that a hung connection does not hang your script forever.
DEFAULT_TIMEOUT = 60.0


class Transport:
    """Sends requests and unwraps replies. One per client."""

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        http: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        headers = {"Accept": "application/json", "User-Agent": _user_agent()}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # An injected client is how the tests run without a network, and how a
        # caller supplies their own proxy, retry or connection-pool policy.
        self._http = http or httpx.Client(timeout=timeout)
        self._http.headers.update(headers)
        self._owns_http = http is None

    # -- the one method everything else goes through ------------------------

    def request(self, method: str, path: str, *, json: Any = None, params: Any = None) -> Any:
        """Make one call and return the decoded body, or raise.

        `path` is relative to the base URL, e.g. ``"/status"``.
        """
        response = self._http.request(
            method,
            self.base_url + path,
            json=json,
            params=_clean(params) if params else None,
        )
        return self._unwrap(response)

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, body: Any = None) -> Any:
        # `{}` rather than `None`: the server expects a JSON object on POST, and
        # sending no body at all is a 400 on some routes.
        return self.request("POST", path, json={} if body is None else body)

    def patch(self, path: str, body: Any = None) -> Any:
        return self.request("PATCH", path, json={} if body is None else body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def stream_sse(self, path: str) -> Iterator[dict]:
        """Yield decoded events from a server-sent-events endpoint.

        Only the ``data:`` lines matter here, and each carries one JSON object.
        Anything that does not parse is skipped rather than raised: a stream is
        meant to be left running, and one malformed frame should not end it.
        """
        with self._http.stream("GET", self.base_url + path) as response:
            if response.status_code >= 400:
                response.read()
                raise errors.from_response(response.status_code, _decode(response))
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    yield _json.loads(line[5:].strip())
                except ValueError:
                    continue

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _unwrap(response: httpx.Response) -> Any:
        payload = _decode(response)
        if response.status_code >= 400:
            raise errors.from_response(response.status_code, payload)
        return payload if payload is not None else {}

    # -- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        if self._owns_http:
            self._http.close()


def _decode(response: httpx.Response) -> Any:
    """Body as JSON, or ``None`` if it is not JSON at all.

    Not every failure comes from the application — a proxy or a load balancer in
    front of it can return HTML — so this must never raise on bad input.
    """
    try:
        return response.json()
    except ValueError:
        return None


def _clean(params: dict) -> dict:
    """Drop ``None`` values so optional query arguments simply go unsent."""
    return {k: v for k, v in params.items() if v is not None}


def _user_agent() -> str:
    from . import __version__

    return f"darkerapi-python/{__version__}"
