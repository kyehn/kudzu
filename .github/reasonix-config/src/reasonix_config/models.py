from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Pricing(BaseModel):
    input: float = 0
    output: float = 0
    cache_hit: float | None = None


class ModelOverride(BaseModel):
    context_window: int | None = None
    max_output: int | None = None
    reasoning_protocol: str | None = None
    supported_efforts: list[str] | None = None
    default_effort: str | None = None
    vision: bool | None = None
    vision_detail: str | None = None
    thinking: str | None = None
    effort: str | None = None
    store: bool | None = None


class ProviderConfig(BaseModel):
    name: str
    kind: str = "openai"
    base_url: str
    chat_url: str | None = None
    models: list[str]
    default: str | None = None
    api_key_env: str | None = None
    context_window: int = 128000
    max_output: int | None = None
    balance_url: str | None = None
    price: Pricing | None = None
    prices: dict[str, Pricing] | None = None
    model_overrides: dict[str, ModelOverride] | None = None
    reasoning_protocol: str | None = None
    supported_efforts: list[str] | None = None
    default_effort: str | None = None
    vision: bool | None = None
    vision_models: list[str] | None = None
    vision_detail: str | None = None
    thinking: str | None = None
    effort: str | None = None
    store: bool | None = None
    headers: dict[str, str] | None = None
    extra_body: dict[str, Any] | None = None
    no_proxy: bool | None = None

    def to_toml(self) -> dict[str, Any]:  # noqa: PLR0912
        d: dict[str, Any] = {"name": self.name, "kind": self.kind, "base_url": self.base_url}
        if self.chat_url:
            d["chat_url"] = self.chat_url
        if len(self.models) == 1:
            d["model"] = self.models[0]
        else:
            d["models"] = self.models
        if self.default:
            d["default"] = self.default
        # api_key_env="" 表示有意不使用 API key (reasonix 会跳过 Authorization header)
        if self.api_key_env is not None:
            d["api_key_env"] = self.api_key_env
        if self.context_window:
            d["context_window"] = self.context_window
        if self.max_output:
            d["max_output"] = self.max_output
        if self.balance_url:
            d["balance_url"] = self.balance_url
        if self.price:
            d["price"] = self.price.model_dump(exclude_none=True)
        if self.prices:
            dump = {k: v.model_dump(exclude_none=True) for k, v in self.prices.items()}
            d["prices"] = dump
        if self.model_overrides:
            dump = {k: v.model_dump(exclude_none=True) for k, v in self.model_overrides.items()}
            d["model_overrides"] = dump
        if self.reasoning_protocol:
            d["reasoning_protocol"] = self.reasoning_protocol
        if self.supported_efforts:
            d["supported_efforts"] = self.supported_efforts
        if self.default_effort:
            d["default_effort"] = self.default_effort
        if self.vision:
            d["vision"] = self.vision
        if self.vision_models:
            d["vision_models"] = self.vision_models
        if self.vision_detail:
            d["vision_detail"] = self.vision_detail
        if self.thinking:
            d["thinking"] = self.thinking
        if self.effort:
            d["effort"] = self.effort
        if self.store is not None:
            d["store"] = self.store
        if self.headers:
            d["headers"] = self.headers
        if self.extra_body:
            d["extra_body"] = self.extra_body
        if self.no_proxy:
            d["no_proxy"] = self.no_proxy
        return d
