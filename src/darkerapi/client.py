"""The client: everything you can do without being in the game.

Reading the service, managing your keys, saved accounts and proxies, and opening
game sessions. Once a session is open, the interesting half lives on
:class:`darkerapi.Session` — see :meth:`DarkerAPI.session`.

The methods are grouped into small namespaces (``.keys``, ``.accounts``,
``.proxies``, ``.sessions``) so that autocomplete is useful and no single class
has forty methods on it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

from ._transport import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, Transport
from .session import Session


class DarkerAPI:
    """Talk to DarkerAPI.

    ::

        from darkerapi import DarkerAPI

        api = DarkerAPI("dnd_your_key_here")
        print(api.status()["status"])

    The public reads — :meth:`status`, :meth:`patch`, :meth:`market`,
    :meth:`items`, :meth:`plans` — need no key at all, so ``DarkerAPI()`` with no
    arguments is a perfectly good way to check whether the game is up.

    Usable as a context manager, which closes the connection pool on the way
    out::

        with DarkerAPI(key) as api:
            ...
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        http: httpx.Client | None = None,
    ):
        """
        :param api_key: A key from the dashboard, ``dnd_...``. Omit for the
            public endpoints only.
        :param base_url: Point this at your own instance if you self-host.
        :param timeout: Seconds. The default is generous because signing a game
            account in genuinely takes a while.
        :param http: Your own ``httpx.Client``, if you need custom proxy, retry
            or connection-pool behaviour. Not closed by this class.
        """
        self._t = Transport(api_key, base_url=base_url, timeout=timeout, http=http)
        self.keys = _Keys(self._t)
        self.accounts = _Accounts(self._t)
        self.proxies = _Proxies(self._t)
        self.sessions = _Sessions(self._t)

    # -- public: no key required --------------------------------------------

    def status(self) -> dict:
        """Is the service up, and is the game up?

        Two different questions. ``status`` is one of ``up``, ``degraded``,
        ``down`` or ``maintenance`` — and ``maintenance`` means IRONMACE has
        taken the game down on purpose, which is not an outage of this service.
        """
        return self._t.get("/status")

    def status_history(self) -> dict:
        """Ninety days of uptime, per component, plus past incidents."""
        return self._t.get("/status/history")

    def patch(self) -> dict:
        """The live game build, and every patch this server has recorded."""
        return self._t.get("/patch")

    def patch_version(self, version: str) -> dict:
        """One build's changelog — every file it modified, added and removed.

        For the live build this also carries the full manifest with hashes.
        """
        return self._t.get(f"/patch/{version}")

    def market(self) -> dict:
        """A snapshot of current marketplace prices.

        Served from a cache the server keeps warm, so this never waits on the
        game and never costs you a game round trip.
        """
        return self._t.get("/market")

    def market_stream(self) -> Iterator[dict]:
        """Prices as they change, as an endless iterator.

        ::

            for tick in api.market_stream():
                print(tick)

        Blocks between events. Stop by breaking out of the loop.
        """
        return self._t.stream_sse("/market/stream")

    def items(
        self,
        q: str | None = None,
        *,
        rarity: str | None = None,
        slot: str | None = None,
        type: str | None = None,
        tag: str | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> dict:
        """Search the item catalog.

        Returns ``{"items": [...], "count", "page", "maxPage", "perPage",
        "totalItems"}``. Each item carries ``tag`` (the stable id), ``label``
        (the display name), ``type``, ``slot``, ``size``, ``stackable``,
        ``tradable`` and ``iconUrl``.

        :param q: Free text, matched against the item's name.
        :param rarity: ``common``, ``uncommon``, ``rare``, ``epic``,
            ``legendary``, ``unique``.
        :param slot: Equipment slot, e.g. ``head``, ``chest``, ``weapon``.
        :param type: Item type, e.g. ``armor``, ``utility``.
        :param tag: An exact item tag, if you already know it.
        """
        return self._t.get(
            "/items", q=q, rarity=rarity, slot=slot, type=type, tag=tag, page=page, limit=limit
        )

    def item(self, tag: str) -> dict:
        """One item and every rarity tier it comes in."""
        return self._t.get(f"/items/{tag}")

    def plans(self) -> dict:
        """The pricing table: what each plan costs and what it allows."""
        return self._t.get("/plans")

    # -- your account --------------------------------------------------------

    def me(self) -> dict:
        """Who this key belongs to, and which plan they are on."""
        return self._t.get("/me")

    def usage(self) -> dict:
        """Credits spent this period, and when the period resets."""
        return self._t.get("/usage")

    def docs(self) -> dict:
        """The API's own reference — every endpoint and every action.

        Handy for discovering actions this library does not wrap; call them with
        :meth:`Session.action`.
        """
        return self._t.get("/docs")

    # -- game sessions -------------------------------------------------------

    def session(self, account_key: str) -> Session:
        """A handle for one connected game account.

        Does not talk to the server — it is just a typed way to address a
        session that :meth:`_Sessions.create` already opened.
        """
        return Session(self._t, account_key)

    # -- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._t.close()

    def __enter__(self) -> DarkerAPI:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Namespaces
#
# Each is a thin grouping over the same transport. They exist so the top-level
# client stays readable, not to hold state.
# ---------------------------------------------------------------------------


class _Namespace:
    def __init__(self, transport: Transport):
        self._t = transport


class _Keys(_Namespace):
    """``api.keys`` — the bearer keys on your account."""

    def list(self) -> dict:
        """Every key you have, by name and prefix. Never the key itself."""
        return self._t.get("/keys")

    def create(self, name: str) -> dict:
        """Mint a key.

        The full ``dnd_...`` value is in the reply and is **never shown again** —
        store it now.
        """
        return self._t.post("/keys", {"name": name})

    def revoke(self, key_id: int) -> dict:
        """Revoke a key by id. Takes effect immediately."""
        return self._t.delete(f"/keys/{key_id}")


class _Accounts(_Namespace):
    """``api.accounts`` — game accounts saved on the server.

    Saving an account lets you open a session by ``label`` instead of sending
    credentials every time. Passwords and Steam shared secrets are encrypted at
    rest and are never returned by :meth:`list`.
    """

    def list(self) -> dict:
        """Your saved accounts. Secrets are omitted."""
        return self._t.get("/accounts")

    def save(
        self,
        label: str,
        username: str,
        *,
        password: str | None = None,
        shared_secret: str | None = None,
        auto_login: bool = False,
        gateway_url: str | None = None,
        method: str = "steam",
    ) -> dict:
        """Save or overwrite an account.

        :param label: Your name for it. This is what you pass as ``label`` to
            :meth:`_Sessions.create`.
        :param shared_secret: The Steam Guard shared secret, if you want the
            server to generate 2FA codes rather than prompting you.
        :param method: ``steam`` (default) or ``blacksmith`` for an IRONMACE
            email login.
        """
        return self._t.post(
            "/accounts",
            _body(
                label=label,
                username=username,
                password=password,
                sharedSecret=shared_secret,
                autoLogin=auto_login,
                gatewayUrl=gateway_url,
                method=method,
            ),
        )

    # `label, /` is positional-only on purpose: it names the account to change,
    # and `**fields` may itself contain a `label` to rename it *to*. Without the
    # marker `update("main", label="renamed")` is a TypeError.
    def update(self, label: str, /, **fields: Any) -> dict:
        """Change some fields of a saved account, leaving the rest alone.

        Accepts the same names as :meth:`save`. Omitting ``password`` keeps the
        stored one rather than clearing it::

            api.accounts.update("main", label="renamed")
        """
        return self._t.patch(f"/accounts/{label}", _body(**fields))

    def delete(self, label: str) -> dict:
        """Forget a saved account and its credentials."""
        return self._t.delete(f"/accounts/{label}")


class _Proxies(_Namespace):
    """``api.proxies`` — the egress used when signing game accounts in."""

    def list(self) -> dict:
        """Your proxies. Passwords are never returned."""
        return self._t.get("/proxies")

    def create(self, url: str, label: str | None = None) -> dict:
        """Add a proxy, e.g. ``socks5://user:pass@host:1080``."""
        return self._t.post("/proxies", _body(url=url, label=label))

    # Positional-only for the same reason as `_Accounts.update` — `**fields`
    # carries a `label`, and the id must not be shadowed by one.
    def update(self, proxy_id: int, /, **fields: Any) -> dict:
        """Change a proxy's ``url``, ``label``, or make it your ``default``."""
        return self._t.patch(f"/proxies/{proxy_id}", _body(**fields))

    def delete(self, proxy_id: int) -> dict:
        """Remove a proxy."""
        return self._t.delete(f"/proxies/{proxy_id}")

    def test(self, proxy_id: int) -> dict:
        """Dial through the proxy and report what came back. Costs 10 credits."""
        return self._t.post(f"/proxies/{proxy_id}/test")

    def pool(self) -> dict:
        """Your standing in the free shared proxy pool, if this server offers one."""
        return self._t.get("/proxies/pool")

    def pool_settings(
        self, *, opt_in: bool | None = None, rotate_on_reconnect: bool | None = None
    ) -> dict:
        """Opt in or out of the free pool, and choose whether to rotate."""
        return self._t.patch(
            "/proxies/pool", _body(optIn=opt_in, rotateOnReconnect=rotate_on_reconnect)
        )

    def switch(self, account_key: str, *, reconnect: bool = True) -> dict:
        """Move a live session onto a fresh proxy. Costs 10 credits."""
        return self._t.post("/proxies/switch", {"accountKey": account_key, "reconnect": reconnect})


class _Sessions(_Namespace):
    """``api.sessions`` — opening and closing game logins."""

    def list(self) -> dict:
        """Every session you currently have open."""
        return self._t.get("/sessions")

    def create(
        self,
        *,
        label: str | None = None,
        account_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        shared_secret: str | None = None,
        email: str | None = None,
        method: str | None = None,
    ) -> dict:
        """Sign a game account in. Costs 25 credits.

        Either name a saved account with ``label``, or pass ``username`` and
        ``password`` inline.

        Returns as soon as the login is *started* — it is not finished yet. Poll
        :meth:`Session.state` until it reads ``in_lobby``::

            api.sessions.create(label="main", account_key="main")
            s = api.session("main")
            while s.state()["state"] != "in_lobby":
                time.sleep(2)

        :param account_key: How you will address this session afterwards. One is
            generated if you do not supply one, and is in the reply.
        """
        return self._t.post(
            "/sessions",
            _body(
                label=label,
                accountKey=account_key,
                username=username,
                password=password,
                sharedSecret=shared_secret,
                email=email,
                method=method,
            ),
        )

    def delete(self, account_key: str) -> dict:
        """Sign the account out and drop the session."""
        return self._t.delete(f"/sessions/{account_key}")

    def reconnect(self, account_key: str) -> dict:
        """Sign a dropped session back in. Costs 25 credits."""
        return self._t.post(f"/sessions/{account_key}/reconnect")

    def guard(self, account_key: str, code: str) -> dict:
        """Answer a Steam Guard prompt with the emailed or app code."""
        return self._t.post(f"/sessions/{account_key}/guard", {"code": code})


def _body(**fields: Any) -> dict:
    """Drop ``None`` values, so an omitted argument is genuinely omitted.

    This matters for PATCH: the server treats a missing field as "leave it
    alone" and an explicit ``null`` as "clear it".
    """
    return {k: v for k, v in fields.items() if v is not None}
