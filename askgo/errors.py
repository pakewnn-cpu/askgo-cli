"""Exit codes and structured error/result types.

Exit codes:
    0 = success
    1 = client / generation error (selector missing, timeout, empty reply, ...)
    2 = not logged in / login expired
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

EXIT_OK = 0
EXIT_CLIENT = 1
EXIT_NOT_LOGGED_IN = 2


class AskGoError(Exception):
    """Raised for any handled failure. Carries exit code + debug context."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int = EXIT_CLIENT,
        step: Optional[str] = None,
        selector: Optional[str] = None,
        screenshot: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.step = step
        self.selector = selector
        self.screenshot = screenshot


@dataclass
class Result:
    """The single JSON object printed to stdout on every invocation."""

    ok: bool = False
    model: Optional[str] = None
    reply: Optional[str] = None
    media: list = field(default_factory=list)
    session_id: Optional[str] = None
    error: Optional[str] = None
    debug: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        # drop None fields for cleaner output, but keep error/debug keys
        for key in ("model", "reply", "session_id"):
            if d.get(key) is None:
                d.pop(key, None)
        # Never let a non-serializable value (e.g. stray bytes) break the
        # "always print JSON" contract: coerce to a safe representation.
        return _sanitize(d)


def _sanitize(obj):
    """Recursively coerce bytes/other non-serializable values to str."""
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", "replace")
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)
