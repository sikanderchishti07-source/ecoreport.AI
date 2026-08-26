"""Error reporting.

When something breaks for a user, this sends the exception to Sentry with the
file, the line and the request that caused it. Today that information only
exists in Render's log, which means someone has to know a fault occurred, find
the right service, and scroll — and a fault nobody reports is a fault nobody
ever hears about. An engineer who hits a bug mid-survey and works around it is
the common case, not the rare one.

Three decisions worth stating, because each of them is the difference between
a tool that gets read and one that gets ignored:

**It is inert without a key.** No `SENTRY_DSN` in the environment and this
does nothing at all — no network calls, no overhead, no behaviour change. The
file can be deployed before anyone has signed up.

**Deliberate refusals are not errors.** "Campaign not found", "no standard
selected", "that link has expired" are the application working correctly. Sent
to Sentry they would bury the real faults under hundreds of routine 404s
within a week, and an inbox nobody trusts is worse than no inbox. Only
unhandled exceptions and genuine server failures are reported.

**Secrets are stripped before anything leaves the building.** Share tokens
appear in portal URLs, and a session cookie or an authorisation header would
otherwise travel with every report. Those are removed here rather than relied
upon to be scrubbed at the far end.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# Query parameters and headers that must never leave the server. Matched
# case-insensitively against the whole name, so "X-Auth-Token" is caught by
# "token".
_SECRET_HINTS = ("token", "secret", "password", "passwd", "authorization",
                 "cookie", "api-key", "apikey", "totp", "otp", "session")

# A share link carries its code in the path. The code is the credential, so
# the path is masked before the event is sent.
_SHARE_PATH = re.compile(r"(/(?:r|share|portal)/)[A-Za-z0-9_\-.]+")


def _looks_secret(name: str) -> bool:
    lowered = str(name).lower()
    return any(hint in lowered for hint in _SECRET_HINTS)


def _scrub(event: Dict[str, Any], _hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Remove credentials from an event on its way out."""
    request = event.get("request") or {}

    headers = request.get("headers")
    if isinstance(headers, dict):
        for name in list(headers):
            if _looks_secret(name):
                headers[name] = "[redacted]"

    cookies = request.get("cookies")
    if cookies:
        request["cookies"] = "[redacted]"

    url = request.get("url")
    if isinstance(url, str):
        request["url"] = _SHARE_PATH.sub(r"\1[redacted]", url)

    query = request.get("query_string")
    if isinstance(query, str) and query:
        parts = []
        for pair in query.split("&"):
            key, _, _value = pair.partition("=")
            parts.append(f"{key}=[redacted]" if _looks_secret(key) else pair)
        request["query_string"] = "&".join(parts)

    # A request body can hold a password on the login route or a whole
    # readings file on an upload. Neither belongs in an error report, and
    # neither is needed to find the fault.
    request.pop("data", None)
    return event


def _is_deliberate_refusal(exc: BaseException) -> bool:
    """True where the exception is the application declining, not failing.

    A 404 for a campaign that does not exist, a 400 for a file with no sample
    columns, a 410 for a withdrawn link: all correct behaviour. Only a 5xx is
    the server itself going wrong.
    """
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and status < 500


def init_sentry() -> bool:
    """Start error reporting if a DSN is configured. Returns whether it did.

    Every failure here is swallowed. Error reporting that stops the
    application from starting is worse than no error reporting.
    """
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        log.warning("SENTRY_DSN is set but sentry-sdk is not installed; "
                    "error reporting is off.")
        return False

    def before_send(event, hint):
        exc_info = (hint or {}).get("exc_info")
        if exc_info and _is_deliberate_refusal(exc_info[1]):
            return None
        return _scrub(event, hint or {})

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            # Personal data is not collected. The username is attached
            # separately where a request has one, which is what actually
            # helps: knowing who hit a fault, without their address or their
            # request body travelling with it.
            send_default_pii=False,
            # Errors only. Performance tracing bills against a separate quota
            # and would exhaust the free allowance on a service that
            # generates reports; it can be turned on later with an
            # environment variable if it is ever wanted.
            traces_sample_rate=float(
                os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0") or 0),
            before_send=before_send,
            # Every event carries the deployed commit, so a fault can be tied
            # to the change that introduced it.
            release=os.environ.get("RENDER_GIT_COMMIT", "")[:12] or None,
            max_breadcrumbs=30,
        )
    except Exception:  # noqa: BLE001
        log.warning("Sentry could not be initialised; the application "
                    "continues without error reporting.", exc_info=True)
        return False

    log.info("Sentry error reporting is on (environment=%s).",
             os.environ.get("SENTRY_ENVIRONMENT", "production"))
    return True


def note_user(username: Optional[str]) -> None:
    """Attach the signed-in username to whatever error follows.

    A username, not an email or an address: enough to ask the person what
    they were doing, and nothing more.
    """
    if not username:
        return
    try:
        import sentry_sdk
        sentry_sdk.set_user({"username": username})
    except Exception:  # noqa: BLE001
        pass
