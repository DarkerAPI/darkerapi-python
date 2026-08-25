"""Every way a DarkerAPI call can fail.

The API returns one error shape for everything::

    {"error": {"code": "credits_exhausted", "message": "..."}}

The codes are stable and documented, so each one gets its own exception class.
That is the whole point of this module: you can write ``except CreditsExhausted``
instead of inspecting a string, and an ``except DarkerAPIError`` at the top of a
script still catches the lot.
"""

from __future__ import annotations


class DarkerAPIError(Exception):
    """Base class. Catch this to catch everything from this library."""

    #: The API's stable error code, e.g. ``"rate_limited"``.
    code: str = "error"

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        if code is not None:
            self.code = code

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class Unauthenticated(DarkerAPIError):
    """No key was sent, or the one sent is not valid.

    Keys look like ``dnd_...`` and are created in the dashboard under API keys.
    """

    code = "unauthenticated"


class PlanLimit(DarkerAPIError):
    """Your plan does not include this, or you have hit one of its limits.

    Raised for both "this feature needs a paid plan" and "you already have as
    many game accounts open as your plan allows".
    """

    code = "plan_limit"


class OperatorOnly(DarkerAPIError):
    """Only the operator of this server can do that.

    Upgrading will not help, which is why it is not a :class:`PlanLimit`.
    """

    code = "operator_only"


class ProxyRequired(DarkerAPIError):
    """This server requires a proxy before it will sign a game account in."""

    code = "proxy_required"


class RateLimited(DarkerAPIError):
    """Too many requests too quickly. Slow down and try again."""

    code = "rate_limited"


class CreditsExhausted(DarkerAPIError):
    """Your credit allowance for this period is used up.

    Credits reset on a rolling 30 days from first use. Only requests made with a
    bearer key are metered.
    """

    code = "credits_exhausted"


class NotFound(DarkerAPIError):
    """No such thing — account, key, proxy, session, item or patch."""

    code = "not_found"


class UnknownAction(DarkerAPIError):
    """No action by that name.

    See :meth:`darkerapi.Session.action` for calling one by name, and the action
    namespaces for the ones this library wraps.
    """

    code = "unknown_action"


class ActionFailed(DarkerAPIError):
    """The action reached the game and the game refused it.

    This is the interesting one: the request was well-formed and you were
    allowed to make it, but the game said no — wrong lobby state, item already
    sold, not enough gold. The message carries the game's own reason.
    """

    code = "action_failed"


class BadRequest(DarkerAPIError):
    """The request body was malformed or a value was out of range."""

    code = "bad_request"


class MissingField(DarkerAPIError):
    """A required field was not supplied."""

    code = "missing_field"


#: Maps the API's error codes to the classes above. Anything unrecognised falls
#: back to :class:`DarkerAPIError`, so a new server-side code is still raised
#: with its message intact rather than crashing this library.
_BY_CODE: dict[str, type[DarkerAPIError]] = {
    cls.code: cls
    for cls in (
        Unauthenticated,
        PlanLimit,
        OperatorOnly,
        ProxyRequired,
        RateLimited,
        CreditsExhausted,
        NotFound,
        UnknownAction,
        ActionFailed,
        BadRequest,
        MissingField,
    )
}


def from_response(status: int, payload: object) -> DarkerAPIError:
    """Build the right exception for one failed response."""
    error = {}
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        error = payload["error"]

    code = str(error.get("code") or "error")
    message = str(error.get("message") or f"Request failed with HTTP {status}.")

    cls = _BY_CODE.get(code, DarkerAPIError)
    return cls(message, code=code, status=status)
