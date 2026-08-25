"""Tests that exercise the client without a network.

`httpx.MockTransport` lets us assert on the exact request the library builds —
method, path, query and body — which is the part that can silently be wrong.
No extra dependency and no live server.
"""

from __future__ import annotations

import httpx
import pytest

from darkerapi import (
    ActionFailed,
    CreditsExhausted,
    DarkerAPI,
    DarkerAPIError,
    NotFound,
    Unauthenticated,
)

BASE = "https://darkerapi.com/api/v1"


def client(handler) -> DarkerAPI:
    """A DarkerAPI whose requests go to `handler` instead of the internet."""
    return DarkerAPI("dnd_test_key", http=httpx.Client(transport=httpx.MockTransport(handler)))


def ok(payload: dict):
    return lambda request: httpx.Response(200, json=payload)


# -- transport ---------------------------------------------------------------


def test_the_key_is_sent_as_a_bearer_token():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, json={})

    client(handler).status()
    assert seen["auth"] == "Bearer dnd_test_key"
    assert seen["ua"].startswith("darkerapi-python/")


def test_no_key_means_no_auth_header():
    """The public endpoints must work without one, not fail differently."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"status": "up"})

    api = DarkerAPI(http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert api.status()["status"] == "up"
    assert seen["auth"] is None


def test_optional_query_arguments_are_omitted_not_sent_as_none():
    """`?rarity=None` would be a filter for the literal string 'None'."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={})

    client(handler).items(q="ruby", rarity=None)
    assert "q=ruby" in seen["url"]
    assert "rarity" not in seen["url"]


def test_optional_body_fields_are_omitted():
    """PATCH treats a missing field as 'leave it alone' — sending null clears it."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    client(handler).accounts.update("main", label="renamed", password=None)
    assert seen["body"] == {"label": "renamed"}


# -- errors ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (401, "unauthenticated", Unauthenticated),
        (402, "credits_exhausted", CreditsExhausted),
        (404, "not_found", NotFound),
        (400, "action_failed", ActionFailed),
    ],
)
def test_each_error_code_becomes_its_own_exception(status, code, expected):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": code, "message": "nope"}})

    with pytest.raises(expected) as caught:
        client(handler).status()
    assert caught.value.code == code
    assert caught.value.message == "nope"
    assert caught.value.status == status


def test_an_unrecognised_code_still_raises_with_its_message():
    """A new server-side code must not crash an old client."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(418, json={"error": {"code": "brand_new", "message": "teapot"}})

    with pytest.raises(DarkerAPIError) as caught:
        client(handler).status()
    assert caught.value.code == "brand_new"
    assert "teapot" in str(caught.value)


def test_a_non_json_failure_does_not_break_the_decoder():
    """A proxy in front of the app can return HTML; that must still raise cleanly."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>Bad Gateway</html>")

    with pytest.raises(DarkerAPIError) as caught:
        client(handler).status()
    assert caught.value.status == 502


# -- endpoints ---------------------------------------------------------------


def test_public_reads_hit_the_documented_paths():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json={})

    api = client(handler)
    api.status()
    api.status_history()
    api.patch()
    api.patch_version("0.17.151.9472")
    api.market()
    api.item("Ruby")
    api.plans()

    assert seen == [
        "GET /api/v1/status",
        "GET /api/v1/status/history",
        "GET /api/v1/patch",
        "GET /api/v1/patch/0.17.151.9472",
        "GET /api/v1/market",
        "GET /api/v1/items/Ruby",
        "GET /api/v1/plans",
    ]


def test_a_custom_base_url_is_respected():
    """Self-hosting must not require patching the library."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={})

    DarkerAPI(
        "dnd_k",
        base_url="http://127.0.0.1:8765/api/v1",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    ).status()
    assert seen["url"] == "http://127.0.0.1:8765/api/v1/status"


# -- sessions and actions ----------------------------------------------------


def test_an_action_posts_to_the_session_action_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    client(handler).session("main").create_character("Grimsby", "Fighter", 0)
    assert seen["path"] == "/api/v1/sessions/main/actions/createCharacter"
    # snake_case in Python, the API's own camelCase on the wire.
    assert seen["body"] == {"nickName": "Grimsby", "characterClass": "Fighter", "gender": 0}


def test_namespaces_map_to_the_right_action_names():
    """The grouping is cosmetic — each method must still call its documented action."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={})

    s = client(handler).session("main")
    s.inventory.carried()
    s.inventory.stash()
    s.merchants.list()
    s.market.best_price("Ruby")
    s.trade.channels()
    s.party.leave()
    s.dungeon.abandon()
    s.character_class()

    assert seen == [
        "inventory",
        "stash",
        "merchants",
        "bestPrice",
        "tradeChannels",
        "partyLeave",
        "abandonGame",
        "class",
    ]


def test_the_escape_hatch_passes_arguments_through_untouched():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    client(handler).session("main").action("somethingNew", camelCase=1, dropped=None)
    assert seen["body"] == {"camelCase": 1}


def test_market_stream_yields_decoded_events_and_skips_junk():
    body = (
        b"event: tick\n"
        b'data: {"item":"Ruby","price":120}\n'
        b"\n"
        b"data: not json at all\n"
        b"\n"
        b'data: {"item":"Sapphire","price":80}\n'
        b"\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    ticks = list(client(handler).market_stream())
    assert ticks == [{"item": "Ruby", "price": 120}, {"item": "Sapphire", "price": 80}]


def test_the_client_closes_its_own_pool_but_not_a_borrowed_one():
    borrowed = httpx.Client(transport=httpx.MockTransport(ok({})))
    with DarkerAPI("dnd_k", http=borrowed) as api:
        api.status()
    assert not borrowed.is_closed, "a client we were handed is the caller's to close"
    borrowed.close()
