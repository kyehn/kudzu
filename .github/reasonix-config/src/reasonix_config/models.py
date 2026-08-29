from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Pricing(BaseModel):
    # models.dev 的 cost 单位是美元; 不设置 currency 时 reasonix 默认按 ¥ 显示
    # (internal/provider/provider.go: Symbol 默认 "¥"), 因此显式标注 USD.
    input: float = 0
    output: float = 0
    cache_hit: float | None = None
    currency: str = "USD"


class ModelOverride(BaseModel):
    # 字段名必须与 reasonix internal/config/config.go ProviderModelOverride 的
    # toml tag 完全一致, 否则会被静默忽略:
    #   reasoning_protocol / supported_efforts / default_effort / vision /
    #   context_window / max_output_tokens
    # (thinking / effort / vision_detail / store 仅存在于 ProviderEntry 级或
    # 根本不存在, 不能放在 model_overrides 里.)
    context_window: int | None = None
    max_output_tokens: int | None = None
    reasoning_protocol: str | None = None
    supported_efforts: list[str] | None = None
    default_effort: str | None = None
    vision: bool | None = None


class ProviderConfig(BaseModel):
    # 字段名必须与 reasonix internal/config/config.go ProviderEntry 的 toml tag
    # 完全一致, 否则会被静默忽略. 注意输出预算字段是 max_output_tokens
    # (不是 max_output); store 字段在 ProviderEntry 中不存在, 不能设置.
    name: str
    kind: str = "openai"
    base_url: str
    chat_url: str | None = None
    models: list[str]
    default: str | None = None
    api_key_env: str | None = None
    context_window: int = 128000
    max_output_tokens: int | None = None
    balance_url: str | None = None
    # kind="responses" 时生效: "stateless" 省略 previous_response_id 续接
    # (reasonix ProviderEntry.ResponsesMode, 上游 opencode go responses 预设同款).
    responses_mode: str | None = None
    price: Pricing | None = None
    prices: dict[str, Pricing] | None = None
    # models.dev 标价一律为美元; 显式标注 provider 级 list-price 币种, 否则
    # reasonix 默认按本地 display_currency 换算, 免费模型价格长期误显示为 ¥0 的
    # 等值而非明确的 USD 0.
    billing_currency: str | None = None
    model_overrides: dict[str, ModelOverride] | None = None
    reasoning_protocol: str | None = None
    supported_efforts: list[str] | None = None
    default_effort: str | None = None
    vision: bool | None = None
    vision_models: list[str] | None = None
    vision_detail: str | None = None
    thinking: str | None = None
    effort: str | None = None
    headers: dict[str, str] | None = None
    extra_body: dict[str, Any] | None = None
    no_proxy: bool | None = None

    def to_toml(self) -> dict[str, Any]:  # noqa: PLR0912, PLR0915
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
        if self.max_output_tokens:
            d["max_output_tokens"] = self.max_output_tokens
        if self.balance_url:
            d["balance_url"] = self.balance_url
        if self.responses_mode:
            d["responses_mode"] = self.responses_mode
        if self.price:
            d["price"] = self.price.model_dump(exclude_none=True)
        if self.prices:
            dump = {k: v.model_dump(exclude_none=True) for k, v in self.prices.items()}
            d["prices"] = dump
        if self.billing_currency:
            d["billing_currency"] = self.billing_currency
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
        if self.headers:
            d["headers"] = self.headers
        if self.extra_body:
            d["extra_body"] = self.extra_body
        if self.no_proxy:
            d["no_proxy"] = self.no_proxy
        return d
