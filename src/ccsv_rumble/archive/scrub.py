"""Credential scrubbing, invoked on the archive write path.

Constitution Principle V requires logs and archived snapshots be scrubbed of
credentials. This runs inside `store.py`'s write, not as a step callers remember
to perform -- a per-call-site discipline is one forgotten call from a leaked token
in a public repository.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

#: Patterns for credential-shaped values. Deliberately broad: a false positive
#: costs a redacted string in an archive nobody reads by hand, while a false
#: negative is a published secret.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"\bey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
)

#: Keys whose value is replaced wholesale regardless of shape.
_SECRET_KEY_HINTS: tuple[str, ...] = (
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
)


def scrub_text(value: str) -> str:
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def scrub(value: Any) -> Any:
    """Recursively redact credential-shaped content from a JSON-able structure."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and any(h in key.lower() for h in _SECRET_KEY_HINTS):
                out[key] = REDACTED
            else:
                out[key] = scrub(item)
        return out
    if isinstance(value, (list, tuple)):
        return [scrub(item) for item in value]
    return value
