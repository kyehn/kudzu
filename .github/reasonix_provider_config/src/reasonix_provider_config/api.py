"""API clients for OpenCode Zen, NVIDIA NIM, and models.dev."""

from __future__ import annotations

import sys

import httpx

from reasonix_provider_config.cache import cached_json
from reasonix_provider_config.models import (
    ModelsDevProvider,
)

OPencode_ZEN_URL = "https://opencode.ai/zen/v1/models"
NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/models"
MODELS_DEV_URL = "https://models.dev/api.json"


def _fetch_openai_models(url: str) -> list[str]:
    """Fetch model IDs from an OpenAI-compatible /v1/models endpoint.

    Exits with code 1 on failure.
    """
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        msg = f"Error: failed to fetch model list from {url}: {exc}\n"
        sys.stderr.write(msg)
        sys.exit(1)

    try:
        parsed = resp.json()
    except ValueError as exc:
        sys.stderr.write(f"Error: invalid JSON from {url}: {exc}\n")
        sys.exit(1)

    # Both APIs return OpenAI-compatible format
    if "data" in parsed:
        model_ids = [item["id"] for item in parsed["data"] if "id" in item]
    else:
        sys.stderr.write(f"Error: unexpected response format from {url}\n")
        sys.exit(1)

    return model_ids


def fetch_zen_models() -> list[str]:
    """Fetch model IDs from OpenCode Zen API.

    Returns all model IDs returned by the API; the caller
    is responsible for filtering to only free models.
    """
    return _fetch_openai_models(OPencode_ZEN_URL)


def fetch_nvidia_models() -> list[str]:
    """Fetch model IDs from NVIDIA NIM API."""
    return _fetch_openai_models(NVIDIA_API_URL)


def fetch_models_dev() -> dict[str, ModelsDevProvider]:
    """Fetch and parse models.dev/api.json.

    Returns a dict mapping provider ID to its data.

    Exits with code 1 on failure.
    """
    raw = cached_json(MODELS_DEV_URL)

    result: dict[str, ModelsDevProvider] = {}
    for provider_id, provider_data in raw.items():
        if not isinstance(provider_data, dict):
            continue
        try:
            provider = ModelsDevProvider.model_validate(
                {"id": provider_id, **provider_data},
            )
        except ValueError as exc:
            sys.stderr.write(
                f"Error: invalid provider data for {provider_id}: {exc}\n",
            )
            sys.exit(1)
        result[provider_id] = provider

    return result
