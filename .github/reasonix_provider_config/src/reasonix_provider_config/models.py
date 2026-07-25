"""Pydantic models for API responses and config."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ModelCost(BaseModel):
    """Pricing info from models.dev."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float | None = None


class ModelLimit(BaseModel):
    """Limits from models.dev."""

    context: int = 0
    output: int = 0


class ReasoningOption(BaseModel):
    """A reasoning option entry from models.dev."""

    type: str = ""
    values: list[str | None] = []
    min: int | None = None


class Modalities(BaseModel):
    """Input/output modalities from models.dev."""

    input: list[str] = []
    output: list[str] = []


class ModelsDevModel(BaseModel):
    """A model entry from models.dev/api.json."""

    id: str
    name: str
    description: str | None = None
    family: str | None = None
    reasoning: bool = False
    reasoning_options: list[ReasoningOption] = []
    tool_call: bool = False
    structured_output: bool = False
    attachment: bool = False
    temperature: bool = True
    modalities: Modalities = Field(default_factory=Modalities)
    knowledge: str | None = None
    release_date: str | None = None
    last_updated: str | None = None
    status: str | None = None
    cost: ModelCost = Field(default_factory=ModelCost)
    limit: ModelLimit = Field(default_factory=ModelLimit)


class ModelsDevProvider(BaseModel):
    """A provider entry from models.dev/api.json."""

    id: str
    name: str
    api: str | None = None
    env: list[str] = []
    models: dict[str, ModelsDevModel] = Field(default_factory=dict)


class ZenModel(BaseModel):
    """Model entry from OpenCode Zen API (OpenAI-compatible list)."""

    id: str
    object: str = "model"


class ZenResponse(BaseModel):
    """Response from OpenCode Zen /v1/models."""

    object: str = "list"
    data: list[ZenModel] = []


class NvidiaModel(BaseModel):
    """Model entry from NVIDIA NIM API (OpenAI-compatible list)."""

    id: str
    object: str = "model"


class NvidiaResponse(BaseModel):
    """Response from NVIDIA NIM /v1/models."""

    object: str = "list"
    data: list[NvidiaModel] = []


class Pricing(BaseModel):
    """Pricing info matching ReasonIX's expected table format.

    Maps to ReasonIX's ``Pricing`` struct — serialised as a TOML table
    with ``input``, ``output``, ``cache_hit`` fields.
    """

    input: float = 0.0
    output: float = 0.0
    cache_hit: float | None = None


class ReasonixProvider(BaseModel):
    """A single provider entry in ReasonIX config.

    Supports both ``model`` (singular string) and legacy ``models`` (list)
    on input — ``models`` is normalised to ``model`` (first entry) during
    validation.

    Additional fields supported by ReasonIX's ProviderEntry (passed via
    ``model_config = {"extra": "allow"}``):
    - ``vision`` (bool): model accepts image input
    - ``vision_detail`` (str): image detail hint: low|high
    - ``thinking`` (str): thinking mode: enabled|disabled|adaptive
    - ``effort`` (str): reasoning effort: high|max|low|medium
    - ``reasoning_protocol`` (str): auto|deepseek|openai|none
    - ``supported_efforts`` (list[str]): custom /effort levels
    - ``default_effort`` (str): default effort level
    - ``prices`` (dict[str, Pricing]): per-model pricing
    - ``headers`` (dict[str, str]): extra HTTP headers
    - ``extra_body`` (dict): extra JSON request body fields
    - ``no_proxy`` (bool): bypass proxy
    """

    name: str
    kind: str = "openai"
    base_url: str
    model: str = ""
    api_key_env: str
    context_window: int = 0
    balance_url: str | None = None
    price: Pricing | None = None
    vision: bool = False
    supported_efforts: list[str] | None = None

    # Pydantic v2 hook called after __init__
    def model_post_init(self, __context: object) -> None:
        """Validate that ``model`` was resolved from input."""
        if not self.model:
            msg = f"Provider '{self.name}' is missing 'model'"
            raise ValueError(msg)

    @model_validator(mode="before")
    @classmethod
    def _normalise_models(cls, data: dict) -> dict:
        """Normalise legacy ``models`` list to ``model`` and legacy ``price`` float to dict."""
        if isinstance(data, dict):
            if "model" not in data and "models" in data:
                models_list = data["models"]
                if isinstance(models_list, list) and len(models_list) > 0:
                    data["model"] = models_list[0]
            # Accept legacy float price (migration) — convert to Pricing or discard
            price = data.get("price")
            if price is not None and not isinstance(price, (dict, Pricing)):
                # Can't map a flat float to input/output — discard for migration
                data["price"] = None
        return data


class ReasonixConfig(BaseModel):
    """The full ReasonIX config.toml structure."""

    providers: list[ReasonixProvider] = []
    # Allow any additional fields
    model_config = {"extra": "allow"}
