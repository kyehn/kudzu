#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://opencode.ai/zen/v1"
MODELS_URL = f"{BASE_URL}/models"
MODELS_DEV_URL = "https://models.dev/api.json"
USER_AGENT = "opencode/2.0.16 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14"
OUTPUT = Path(os.environ.get("DSH_SETTINGS", Path.home() / ".dsh/settings.yaml"))

_RANDOM_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_identifier_state = {"timestamp": 0, "counter": 0}


def identifier(descending: bool) -> str:
    """26-char opencode id: 12 hex chars of (ms << 12 | counter) — bitwise-NOT'ed
    when descending — plus 14 random base62 chars. Mirrors identifier() in
    .github/pi-opencode/shared.ts, so the wire shape matches without a hardcoded
    session id baked into the repo."""
    now = int(time.time() * 1000)
    if now != _identifier_state["timestamp"]:
        _identifier_state["timestamp"] = now
        _identifier_state["counter"] = 0
    _identifier_state["counter"] += 1
    current = now * 0x1000 + _identifier_state["counter"]
    value = ~current if descending else current
    time_part = "".join(
        f"{(value >> (40 - 8 * index)) & 0xFF:02x}" for index in range(6)
    )
    return time_part + "".join(secrets.choice(_RANDOM_CHARS) for _ in range(14))


def get_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "x-opencode-client": "cli"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def is_alive(model_id: str) -> bool:
    """Probe the model once; only a kill signal excludes it from the catalog.

    Alive: 2xx, plus free-tier/auth/rate gating (401/403/429) and upstream
    5xx — those responses mean the model still exists. Dead: the explicit
    400 "Model is unavailable", any other 4xx (not routed upstream), and
    transport failures — fail-closed, so a model that cannot be proven
    reachable never reaches the catalog.
    """
    body = json.dumps(
        {"model": model_id, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 4}
    ).encode()
    request = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer public",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return True
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", "replace")
        if error.code == 400 and "Model is unavailable" in payload:
            return False
        return error.code in {401, 403, 429} or 500 <= error.code < 600
    except (urllib.error.URLError, TimeoutError):
        return False


def main() -> None:
    provider = get_json(MODELS_DEV_URL)["opencode"]
    listed = {model["id"] for model in get_json(MODELS_URL).get("data", [])}
    models = []
    for model_id in sorted(listed):
        model = provider.get("models", {}).get(model_id)
        cost = model.get("cost") if model else None
        if not isinstance(cost, dict) or cost.get("input") != 0 or cost.get("output") != 0:
            continue
        if model.get("status") == "deprecated":
            print(f"skip deprecated model: {model_id}", file=sys.stderr)
            continue
        package = (model.get("provider") or {}).get("npm")
        if package in {"@ai-sdk/openai", "@ai-sdk/anthropic"}:
            continue
        modalities = (model.get("modalities") or {}).get("input", [])
        if model.get("tool_call") is False or "text" not in (modalities or ["text"]):
            continue
        if not is_alive(model_id):
            print(f"skip unavailable model: {model_id}", file=sys.stderr)
            continue
        limits = model.get("limit") or {}
        models.append(
            (
                model_id,
                limits.get("context") or 200000,
                limits.get("output") or 32000,
            )
        )
    if not models:
        raise SystemExit("refusing to write an empty DSH model catalog")
    session_id = f"ses_{identifier(descending=True)}"
    request_id = f"msg_{identifier(descending=False)}"
    lines = [
        "llm-pi-ai:",
        "  providers:",
        "    zen:",
        "      displayName: zen",
        "      api: openai-completions",
        f"      baseURL: {BASE_URL}",
        "      apiKeyEnv: OPENCODE_PUBLIC",
        "      headers:",
        f"        User-Agent: {USER_AGENT}",
        "        x-opencode-client: cli",
        "        x-opencode-project: global",
        f"        x-opencode-session: {session_id}",
        f"        x-opencode-request: {request_id}",
        "      models:",
    ]
    for model_id, context_window, max_tokens in models:
        lines.extend(
            [
                f"        - id: {model_id}",
                "          api: openai-completions",
                f"          contextWindow: {context_window}",
                f"          maxOutputTokens: {max_tokens}",
            ]
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(models)} DSH models to {OUTPUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
