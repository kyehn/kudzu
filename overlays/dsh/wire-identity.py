#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3
"""opencode wire-identity algorithm, ported from .github/pi-opencode/index.ts.

Byte-for-byte what opencode's ``iC()`` builds: six bytes of
``(Date.now() * 0x1000 + counter)`` taken from the low 48 bits (bit-inverted
in full for a descending id) as 12 hex chars, then 14 base62 chars from a
CSPRNG. One counter shared by every id kind; it resets each millisecond and
the first id of a millisecond carries 1. Never baked in: every call
recomputes.

Consumed by the ``opencode-wire`` bundle plugin at request time; this module
is the executable reference, not a static header value.
"""

from __future__ import annotations

import json
import secrets
import time

OPENCODE_VERSION = "1.18.32"
BUN_VERSION = "1.3.14"
USER_AGENT_BY_API = {
    "openai-completions": (
        f"opencode/{OPENCODE_VERSION} ai-sdk/provider-utils/4.0.23"
        f" runtime/bun/{BUN_VERSION}"
    ),
    "openai-responses": (
        f"opencode/{OPENCODE_VERSION} ai-sdk/provider-utils/4.0.40"
        f" runtime/bun/{BUN_VERSION}"
    ),
    "anthropic-messages": (
        f"opencode/{OPENCODE_VERSION} ai-sdk/provider-utils/4.0.46"
        f" runtime/bun/{BUN_VERSION}"
    ),
}

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


class _Sequence:
    """Per-millisecond counter shared by every id kind (opencode `iC`)."""

    def __init__(self) -> None:
        self.counter = 0
        self.last_ms = 0

    def next(self, now_ms: int) -> int:
        if now_ms != self.last_ms:
            self.last_ms = now_ms
            self.counter = 0
        self.counter += 1
        return (now_ms * 0x1000 + self.counter) & 0xFFFFFFFFFFFF


_sequence = _Sequence()


def identifier(*, descending: bool) -> str:
    packed = _sequence.next(time.time_ns() // 1_000_000)
    value = (~packed & 0xFFFFFFFFFFFF) if descending else packed
    scope = format(value, "012x")
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(14))
    return scope + suffix


def wire_identity(api: str, session_id: str) -> dict[str, str]:
    headers = {
        "x-opencode-client": "cli",
        "x-opencode-project": "global",
        "x-opencode-session": session_id,
        "x-opencode-request": f"msg_{identifier(descending=False)}",
    }
    if api in USER_AGENT_BY_API:
        headers["User-Agent"] = USER_AGENT_BY_API[api]
    return headers


def new_session_id() -> str:
    return f"ses_{identifier(descending=True)}"


if __name__ == "__main__":
    session = new_session_id()
    print(json.dumps(wire_identity("openai-completions", session), indent=2))
