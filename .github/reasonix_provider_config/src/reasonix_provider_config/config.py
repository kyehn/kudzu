"""Read and write ReasonIX config.toml."""

from __future__ import annotations

import sys
from pathlib import Path

import tomli
import tomli_w

from reasonix_provider_config.models import ReasonixConfig

CONFIG_PATH = Path.home() / ".reasonix" / "config.toml"


def read_config() -> ReasonixConfig:
    """Read and parse ~/.reasonix/config.toml.

    Exits with code 1 if the file doesn't exist or is invalid.
    """
    if not CONFIG_PATH.is_file():
        sys.stderr.write(
            f"Error: config file not found: {CONFIG_PATH}\n",
        )
        sys.exit(1)

    raw = CONFIG_PATH.read_bytes()
    try:
        parsed = tomli.loads(raw.decode())
    except (tomli.TOMLDecodeError, UnicodeDecodeError) as exc:
        sys.stderr.write(
            f"Error: failed to parse {CONFIG_PATH}: {exc}\n",
        )
        sys.exit(1)

    try:
        config = ReasonixConfig.model_validate(parsed)
    except ValueError as exc:
        sys.stderr.write(
            f"Error: invalid config schema in {CONFIG_PATH}: {exc}\n",
        )
        sys.exit(1)

    return config


def write_config(config: ReasonixConfig) -> None:
    """Write config back to ~/.reasonix/config.toml.

    Exits with code 1 on write failure.
    """
    try:
        data = config.model_dump(
            mode="python",
            exclude_none=True,
        )
        toml_str = tomli_w.dumps(data)
        CONFIG_PATH.write_text(toml_str)
    except (OSError, ValueError) as exc:
        sys.stderr.write(
            f"Error: failed to write {CONFIG_PATH}: {exc}\n",
        )
        sys.exit(1)
