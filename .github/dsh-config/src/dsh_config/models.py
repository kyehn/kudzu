from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Pricing(BaseModel):
    # models.dev 的 cost 单位是美元; dsh 端仅透传, 保留原币种.
    input: float = 0
    output: float = 0
    cache_hit: float | None = None
    currency: str = "USD"


class ModelEntry(BaseModel):
    # llm-pi-ai settings.yaml 的 models 数组元素 (modelProfile):
    # id / name / contextWindow / maxTokens / reasoningEfforts / compat.
    id: str
    name: str | None = None
    context_window: int | None = None
    max_tokens: int | None = None
    reasoning_efforts: list[str] | bool | None = None

    def to_entry(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id}
        if self.name:
            d["name"] = self.name
        if self.context_window:
            d["contextWindow"] = self.context_window
        if self.max_tokens:
            d["maxTokens"] = self.max_tokens
        if isinstance(self.reasoning_efforts, bool):
            d["reasoningEfforts"] = self.reasoning_efforts
        elif self.reasoning_efforts:
            d["reasoningEfforts"] = self.reasoning_efforts
        return d


class ProviderProfile(BaseModel):
    # llm-pi-ai settings.yaml 的 provider profile:
    # apiKeyEnv / displayName / api / baseURL / models.
    name: str
    kind: str = "openai"
    base_url: str
    api: str = "openai-completions"
    models: list[ModelEntry]
    default: str | None = None
    api_key_env: str | None = None
    headers: dict[str, str] | None = None

    def to_profile(self) -> dict[str, Any]:
        d: dict[str, Any] = {"displayName": self.name}
        if self.api_key_env is not None:
            d["apiKeyEnv"] = self.api_key_env
        d["api"] = self.api
        d["baseURL"] = self.base_url
        d["models"] = [m.to_entry() for m in self.models]
        if self.headers:
            d["headers"] = self.headers
        return d
