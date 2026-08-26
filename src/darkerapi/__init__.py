"""The official Python client for DarkerAPI — the Dark and Darker API.

::

    from darkerapi import DarkerAPI

    api = DarkerAPI("dnd_your_key_here")

    # Public reads need no key at all.
    print(api.status()["status"])

    # Signing a game account in and reading its stash.
    api.sessions.create(label="main", account_key="main")
    stash = api.session("main").inventory.stash()

See https://darkerapi.com/docs for the full API reference.
"""

from __future__ import annotations

__version__ = "0.1.1"

from ._transport import DEFAULT_BASE_URL
from .client import DarkerAPI
from .errors import (
    ActionFailed,
    BadRequest,
    CreditsExhausted,
    DarkerAPIError,
    MissingField,
    NotFound,
    OperatorOnly,
    PlanLimit,
    ProxyRequired,
    RateLimited,
    Unauthenticated,
    UnknownAction,
)
from .session import Session

__all__ = [
    "DarkerAPI",
    "Session",
    "DEFAULT_BASE_URL",
    "__version__",
    # Errors, in the order they are documented.
    "DarkerAPIError",
    "Unauthenticated",
    "PlanLimit",
    "OperatorOnly",
    "ProxyRequired",
    "RateLimited",
    "CreditsExhausted",
    "NotFound",
    "UnknownAction",
    "ActionFailed",
    "BadRequest",
    "MissingField",
]
