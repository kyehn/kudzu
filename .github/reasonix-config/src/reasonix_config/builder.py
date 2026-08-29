"""OpenCode Zen / NVIDIA NIM 免费模型 → reasonix config.toml 生成器.

models.dev 模型条目 (opencode/nvidia) 字段与 reasonix 配置的对应关系:

  id                     → models 列表 / model_overrides key / prices key
  limit.context          → context_window (model_overrides, provider 取组内最大值)
  limit.output           → max_output_tokens (model_overrides)
  reasoning (bool)       → reasoning_protocol="openai" (model_overrides)
  reasoning_options      → effort 类型取 supported_efforts + default_effort
                           (取最高档; toggle/budget_tokens 类型无 reasonix 对应项,
                           toggle 只声明 reasoning_protocol)
  attachment / modalities.input 含 "image" → vision=true (model_overrides)
  provider.npm           → zen 网关 wire 协议: "@ai-sdk/openai" = Responses
                           (kind="responses", responses_mode="stateless"),
                           其他 = chat completions (kind="openai")
  cost.input/output/cache_read → prices (per-model, USD; cache_write 与
                           tiers/context_over_200k 分层定价 reasonix Pricing
                           不支持, 不入配置)
  status=deprecated      → 过滤
  其余字段 (name/description/family/tool_call/structured_output/temperature/
  knowledge/release_date/open_weights/interleaved) 为客户端/展示元数据,
  reasonix 配置无对应项.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from reasonix_config.fetcher import fetch_models_dev, fetch_zen_models
from reasonix_config.models import ModelOverride, Pricing, ProviderConfig

REASONIX_CONFIG = Path.home() / ".reasonix" / "config.toml"
MIN_CHAT_CONTEXT = 8000
# 与上游 DeepSeek-Reasonix Default().ConfigVersion 同步 (v1.33.0 = 7)。
# 钉旧值会让每次部署后的首次启动触发 ApplyUserConfigUpgradesOnStartup
# 迁移重写整个 config.toml (billing/pricing 默认值物化), 下一轮部署又
# 被钉回, 形成无谓的迁移循环。
CONFIG_VERSION = 7

PROVIDER_NAMES = ("opencode", "nvidia")

# models.dev cost 字段单位为美元 (USD); reasonix 未显式标注币种时按本地
# display_currency 显示, 免费模型会被误读为 ¥0 的等值而非明确的 USD 0。
# 因此在 provider 级固化为 USD, 保证价格语义正确。
BILLING_CURRENCY = "USD"

# models.dev 模型的 provider.npm 声明 opencode 客户端实际使用的 SDK 包, 由此
# 推断 zen 网关 /zen/v1 上的 wire 协议:
#   - "@ai-sdk/openai"           → OpenAI Responses   (POST {base_url}/responses)
#   - 其他 / 缺省 (openai-compatible) → chat completions (POST {base_url}/chat/completions)
# 实测 (2026-08): 免费集中 muse-spark-1.2-contributor-free 是唯一 Responses
# 模型, chat/completions 对它返回 HTTP 500, /responses 正常。reasonix 里
# 两种 wire 由 provider kind 区分: "openai" → /chat/completions, "responses"
# → /responses (stateless, 与上游 opencode go responses 预设一致)。
RESPONSES_SDK_PACKAGE = "@ai-sdk/openai"

# models.dev 字段级覆盖率审计。reasonix/pi 只消费下列字段, 其余为展示或
# 运行时自适应 (无对应可设字段)。两集合并集必须覆盖 opencode/nvidia provider
# 下每一个真实出现的 key, 否则 TestFieldCoverage 会失败——新增字段须在此显式
# 归类 (handled 或 ignored), 不允许静默遗漏。
MODEL_FIELD_HANDLED: frozenset[str] = frozenset(
    {
        "id",  # 用作模型 key, 不参与覆盖映射
        "limit",  # context/output -> context_window/max_output_tokens
        "cost",  # input/output/cache_read -> Pricing
        "modalities",  # output 含 text 决定可否作聊天模型; input 含 image -> vision
        "attachment",  # True -> vision
        "reasoning",  # True -> reasoning_protocol
        "reasoning_options",  # effort 类型 -> supported_efforts/default_effort
        "status",  # deprecated -> 剔除
        "tool_call",  # False -> 非 agent 模型, 剔除
        "provider",  # npm -> 模型 wire 协议 (chat / responses), 见 _wire_kind
    }
)
MODEL_FIELD_IGNORED: frozenset[str] = frozenset(
    {
        "name",  # 展示名
        "description",  # 展示描述
        "family",  # 展示分类
        "knowledge",  # 知识截止日期, 展示
        "last_updated",  # 元数据时间戳, 展示
        "release_date",  # 展示
        "open_weights",  # 展示/许可
        "interleaved",  # 运行时自适应: 工具调用交错由 reasonix 按协议决定, 无对应字段
        "structured_output",  # 运行时自适应: 由模型能力注册表驱动, 无对应字段
        "temperature",  # 运行时自适应: 采样温度由 reasonix 控制, 无对应字段
    }
)
PROVIDER_FIELD_HANDLED: frozenset[str] = frozenset(
    {
        "api",  # -> base_url
        "env",  # env[0] -> api_key_env
        "models",  # -> models / model_overrides / prices
    }
)
PROVIDER_FIELD_IGNORED: frozenset[str] = frozenset(
    {
        "id",  # 我们固定 provider name (opencode/nvidia)
        "npm",  # 内部 SDK 包名, provider 级无 wire 判定用途
        "name",  # 展示名
        "doc",  # 文档链接
    }
)


def _build_override(m: dict[str, Any]) -> dict[str, Any]:
    """从 models.dev 元数据构建 model_overrides 条目.

    输出字段名与 reasonix ProviderModelOverride 的 toml tag 严格一致:
    context_window / max_output_tokens / reasoning_protocol / supported_efforts /
    default_effort / vision. (thinking 仅存在于 ProviderEntry 级, 不放这里.)

    models.dev 字段映射审计 (见 MODEL_FIELD_HANDLED / MODEL_FIELD_IGNORED):
      limit.context         -> context_window        (缺失/0 不写, 继承 provider 级)
      limit.output          -> max_output_tokens      (缺失/0 不写)
      limit.input           -> (忽略, reasonix 无独立输入预算字段)
      reasoning == True     -> reasoning_protocol="openai"
      reasoning_options[].type=="effort"
                            -> supported_efforts / default_effort (取末个非 none 值)
      reasoning_options[].type=="toggle"
                            -> 仅声明 reasoning_protocol (无 effort 等级)
      attachment / modalities.input 含 image
                            -> vision=True
      cost                 -> 见 _price_of (落到 provider.prices[mid], 非 override)
      modalities.output     -> _is_chat_model 用其含 text 决定收录
      tool_call            -> _is_chat_model 用其 False 决定剔除
      status               -> build_* 用 deprecated 决定剔除
    """
    override: dict[str, Any] = {}
    ctx = m.get("limit", {}).get("context", 0)
    if ctx:
        override["context_window"] = ctx
    max_output = m.get("limit", {}).get("output", 0)
    if max_output:
        override["max_output_tokens"] = max_output
    reasoning_options = m.get("reasoning_options", [])
    if m.get("reasoning", False):
        override["reasoning_protocol"] = "openai"
        for opt in reasoning_options:
            if isinstance(opt, dict) and opt.get("type") == "effort":
                values = [v for v in opt.get("values", []) if v is not None]
                if values:
                    override["supported_efforts"] = values
                    # 取最高级别: 最后一个非 "none" 的值
                    non_none = [v for v in values if v != "none"]
                    override["default_effort"] = non_none[-1] if non_none else values[-1]
                    break
    modalities_input = m.get("modalities", {}).get("input", [])
    if m.get("attachment") or ("image" in (modalities_input or [])):
        override["vision"] = True
    return override


def _price_of(m: dict[str, Any]) -> Pricing | None:
    """从 models.dev cost 字段解析单模型价格 (落到 provider.prices[mid]).

    映射: cost.input -> input, cost.output -> output, cost.cache_read -> cache_hit;
    cost.cache_write 等其余分项 reasonix Pricing 无对应字段, 忽略。单位美元,
    显式标 USD (见 Pricing.currency)。数值合法性交由 pydantic 校验, 非法输入
    直接抛 ValidationError. 三项全零视为免费, 返回 None 不入表。
    """
    cost = m.get("cost", {})
    price = Pricing(
        input=cost.get("input", 0),
        output=cost.get("output", 0),
        cache_hit=cost.get("cache_read"),
    )
    if price.input or price.output or price.cache_hit:
        return price
    return None


def _is_chat_model(mid: str, mdata: dict[str, Any]) -> bool:
    """Whether a models.dev entry is usable as an agentic chat model.

    Covers every models.dev field reasonix/pi need to decide inclusion:
    - limit.context >= MIN_CHAT_CONTEXT (token budget large enough to converse)
    - modalities.output must contain "text": pure image/video/audio generators
      (flux, cosmos, whisper, tts) slip past the name filter but cannot answer
      in text, so they must be pruned here.
    - tool_call must not be False: an agent requires tool calling; entries with
      tool_call=True or a missing key stay (legacy entries omit the field), only
      an explicit False is pruned (e.g. bge-m3 / phi-4-multimodal / paligemma).
    - name skip_patterns exclude embedding/guard/tts/rerank/... special models.
    """
    limit = mdata.get("limit", {})
    if limit.get("context", 0) < MIN_CHAT_CONTEXT:
        return False
    modalities = mdata.get("modalities", {}) or {}
    if (modalities.get("output") or []) and "text" not in modalities["output"]:
        return False
    if mdata.get("tool_call") is False:
        return False
    name_lower = mid.lower()
    skip_patterns = [
        "embed",
        "guard",
        "safety",
        "tts",
        "voice",
        "audio",
        "cosmos-predict",
        "cosmos-transfer",
        "flux",
        "image",
        "edit",
        "rerank",
        "esm",
        "detection",
        "synthetic",
        "validate",
        "whisper",
        "bevformer",
        "streampetr",
        "studiovoice",
        "sparsedrive",
        "usd",
        "riva",
        "magpie",
        "active-speaker",
        "gliner",
    ]
    return all(pat not in name_lower for pat in skip_patterns)


def get_free_zen_model_ids(zen_data: dict[str, Any], md_models: dict[str, Any]) -> set[str]:
    """Zen 在售模型中的免费集.

    判定与 pi-opencode 同规则: 名字带 "-free" (zen 免费层命名约定), 或
    models.dev 已收录且标价 input/output 均为零 (缺 cost 字段视同零,
    big-pickle 等无后缀免费模型由此收录, 不再逐个硬编码). models.dev
    未收录的非 -free id 一律排除: 条目缺失与标价缺失不同, 前者无法证明
    免费, 误收会导致无标价模型进入配置甚至成为排序最前的 default.
    """
    ids: set[str] = set()
    for m in zen_data.get("data", []):
        mid = m["id"]
        if "-free" in mid:
            ids.add(mid)
            continue
        mdata = md_models.get(mid)
        if mdata is None:
            continue
        cost = mdata.get("cost") or {}
        if not cost.get("input") and not cost.get("output"):
            ids.add(mid)
    return ids


def _wire_kind(m: dict[str, Any] | None) -> str:
    """models.dev 元数据 → reasonix provider kind (openai | responses).

    provider.npm 缺失 (zen 有而 models.dev 未收录) 时按 chat completions
    处理: 免费集实测所有此类模型 (big-pickle 等) 均走 chat 端点.
    """
    if m is None:
        return "openai"
    npm = (m.get("provider") or {}).get("npm")
    return "responses" if npm == RESPONSES_SDK_PACKAGE else "openai"


def _build_opencode_wire_provider(
    name: str,
    kind: str,
    entries: list[tuple[str, dict[str, Any] | None]],
    provider: dict[str, Any],
) -> ProviderConfig | None:
    """组装单个 wire 协议的 opencode provider (models/overrides/价格/default)."""
    if not entries:
        return None

    models_list: list[str] = []
    model_prices: dict[str, Pricing] = {}
    model_overrides: dict[str, ModelOverride] = {}
    max_context = 0

    for mid, m in entries:
        models_list.append(mid)
        if m is None:
            continue
        max_context = max(max_context, m.get("limit", {}).get("context", 0))
        price = _price_of(m)
        if price:
            model_prices[mid] = price
        override = _build_override(m)
        if override:
            model_overrides[mid] = ModelOverride(**override)

    return ProviderConfig(
        name=name,
        kind=kind,
        base_url=provider["api"],
        models=models_list,
        default=models_list[0],
        api_key_env=provider["env"][0],
        context_window=max_context,
        prices=model_prices or None,
        model_overrides=model_overrides or None,
        billing_currency=BILLING_CURRENCY,
        # Responses 网关无状态: 不续接 previous_response_id
        responses_mode="stateless" if kind == "responses" else None,
        headers=None,
    )


def build_opencode(md_data: dict, zen_data: dict) -> list[ProviderConfig]:
    """OpenCode Zen 免费模型, 按 wire 协议拆分为 provider 列表.

    zen /zen/v1 是单网关, 但模型族没有通用的 chat completions 端点; 每个
    模型在 models.dev 的 provider.npm 声明其真实协议. 主 provider "opencode"
    承载 chat completions 模型, Responses 模型 (当前为
    muse-spark-1.2-contributor-free) 拆分到 "opencode-responses", 否则
    chat/completions 对它返回 HTTP 500 导致模型不可用.

    api_key_env 取 models.dev env 首项; reasonix 从 .env 读 key 并发送
    Authorization: Bearer public (匹配 opencode 客户端默认行为), 每次
    reasonix-config 运行自动确保 ~/.reasonix/.env 中有该条目.

    opencode 头部 (User-Agent / x-opencode-* / utls TLS 指纹) 由 reasonix
    源码检测到该 provider 后动态生成, 因此这里不写静态 headers, 避免与
    源码重复; X-Opencode-Session / X-Opencode-Request 为动态 ID, 静态
    配置本就无法表达.
    """
    provider = md_data["opencode"]
    models_raw = provider["models"]

    by_wire: dict[str, list[tuple[str, dict[str, Any] | None]]] = {
        "openai": [],
        "responses": [],
    }
    for mid in sorted(get_free_zen_model_ids(zen_data, models_raw)):
        m = models_raw.get(mid)
        if m is not None and m.get("status") == "deprecated":
            continue
        # zen 有而 models.dev 未收录的模型仍收录 (无元数据优于不可用).
        by_wire[_wire_kind(m)].append((mid, m))

    providers: list[ProviderConfig] = []
    for kind in ("openai", "responses"):
        name = "opencode" if kind == "openai" else "opencode-responses"
        cfg = _build_opencode_wire_provider(name, kind, by_wire[kind], provider)
        if cfg is not None:
            providers.append(cfg)

    if not providers:
        msg = "No free OpenCode Zen models found"
        raise SystemExit(msg)
    return providers


def build_nvidia(md_data: dict) -> ProviderConfig:
    """NVIDIA NIM 聊天模型, 字段遵循 models.dev 的 nvidia provider 条目."""
    provider = md_data["nvidia"]
    models_raw = provider["models"]

    models_list: list[str] = []
    model_prices: dict[str, Pricing] = {}
    model_overrides: dict[str, ModelOverride] = {}
    max_context = 0

    for mid, m in sorted(models_raw.items()):
        if m.get("status") == "deprecated":
            continue
        if not _is_chat_model(mid, m):
            continue
        models_list.append(mid)
        max_context = max(max_context, m.get("limit", {}).get("context", 0))
        price = _price_of(m)
        if price:
            model_prices[mid] = price
        override = _build_override(m)
        if override:
            model_overrides[mid] = ModelOverride(**override)

    if not models_list:
        msg = "No NVIDIA NIM chat models found"
        raise SystemExit(msg)

    return ProviderConfig(
        name="nvidia",
        kind="openai",
        base_url=provider["api"],
        models=models_list,
        default=models_list[0],
        api_key_env=provider["env"][0],
        context_window=max_context,
        prices=model_prices or None,
        model_overrides=model_overrides or None,
        billing_currency=BILLING_CURRENCY,
    )


def build_all(providers_filter: list[str] | None = None) -> list[ProviderConfig]:
    wanted = set(providers_filter) if providers_filter is not None else set(PROVIDER_NAMES)
    md_data = fetch_models_dev()
    providers: list[ProviderConfig] = []
    if "opencode" in wanted:
        providers.extend(build_opencode(md_data, fetch_zen_models()))
    if "nvidia" in wanted:
        providers.append(build_nvidia(md_data))
    return providers


def _ensure_opencode_public_key() -> None:
    """Ensure ``OPENCODE_API_KEY`` exists in ``~/.reasonix/.env``.

    opencode Zen 接受 ``Bearer public`` 作为匿名凭据, 缺失时补上 ``public``
    保证开箱即用. 已有值必须原样保留: 用户可能用自己的 key 走付费模型或
    独立配额, 静默降级成共享匿名凭据会破坏认证与限流. 重复行折叠为第一行
    的原值.
    """
    env_path = REASONIX_CONFIG.parent / ".env"
    key = "OPENCODE_API_KEY"
    prefix = f"{key}="

    if env_path.exists():
        existing_lines = env_path.read_text().splitlines()
        seen = False
        new_lines: list[str] = []
        for old_line in existing_lines:
            stripped = old_line.strip()
            if stripped == "" or stripped.startswith("#"):
                new_lines.append(old_line)
            elif stripped.startswith(prefix):
                if not seen:  # 保留第一个原值, 后续重复行丢弃
                    new_lines.append(stripped)
                    seen = True
            else:
                new_lines.append(old_line)
        if not seen:
            new_lines.append(f"{prefix}public")
            new_lines.append("")
        env_path.write_text("\n".join(new_lines) + "\n")
        # .env 含 API 密钥, 统一收紧为仅属主可读写 (新建与更新一致)
        env_path.chmod(0o600)
    else:
        env_path.write_text(f"{prefix}public\n")
        env_path.chmod(0o600)


def _run_reasonix_doctor() -> None:
    """Validate config by running ``reasonix doctor``. Exit on failure."""
    doctor = shutil.which("reasonix")
    if doctor is None:
        sys.stderr.write("warning: 'reasonix' not found on PATH; skipping doctor validation\n")
        return
    try:
        result = subprocess.run(  # noqa: S603 — resolved by shutil.which()
            [doctor, "doctor"],
            timeout=30,
            check=False,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        msg = "'reasonix doctor' timed out after 30s"
        raise SystemExit(msg) from None
    except OSError as exc:
        msg = f"failed to run 'reasonix doctor': {exc}"
        raise SystemExit(msg) from None
    if result.returncode != 0:
        msg = f"'reasonix doctor' exited with code {result.returncode}"
        if result.stderr:
            msg += f"\n{result.stderr.decode(errors='replace').strip()}"
        raise SystemExit(msg)


def write_config(providers: list[ProviderConfig]) -> Path:
    """Read existing config, replace matching providers, and write back.

    - Removes old provider entries whose name matches a new provider.
    - Appends new providers.
    - If ``default_model`` existed but is no longer valid, picks the first
      model of the first provider as replacement.
    - Validates via ``reasonix doctor``.
    - Ensures ``OPENCODE_API_KEY=public`` in reasonix ``.env``.
    """
    config_path = REASONIX_CONFIG
    if not config_path.exists():
        msg = f"config file {config_path} does not exist; run `reasonix setup` first"
        raise SystemExit(msg)

    with config_path.open("rb") as f:
        existing = tomllib.load(f)

    existing["config_version"] = CONFIG_VERSION

    # 删除与新增 provider 同名的旧条目
    new_names = {p.name for p in providers}
    old_providers = existing.get("providers", [])
    existing["providers"] = [p for p in old_providers if p.get("name") not in new_names]
    existing["providers"].extend(p.to_toml() for p in providers)

    # 检查现有的 default_model 是否合法, 不合法则自动修正
    _repair_default_model(existing, providers)

    config_path.write_text(tomli_w.dumps(existing))

    _ensure_opencode_public_key()
    _run_reasonix_doctor()

    return config_path


def _repair_default_model(
    existing: dict[str, Any],
    providers: list[ProviderConfig],
) -> None:
    """If ``default_model`` exists but isn't valid, reset to first available model.

    有效引用集合 = 新 provider 的模型/名字 + 保留的旧 provider 的模型/名字
    (default_model 可能指向未参与本次更新的其他 provider, 不能误判为无效).
    """
    ref = existing.get("default_model")
    if ref is None:
        return

    valid_bare: set[str] = set()
    valid_names: set[str] = set()
    for p in providers:
        valid_names.add(p.name)
        valid_bare.update(p.models)

    new_names = {p.name for p in providers}
    for p in existing.get("providers", []):
        name = p.get("name")
        if name in new_names:
            continue  # 该 provider 即将被本次更新替换, 其模型不再有效
        if name:
            valid_names.add(name)
        if p.get("models"):
            valid_bare.update(p["models"])
        elif p.get("model"):
            valid_bare.add(p["model"])

    if not valid_bare:
        return

    # 检查 ref 是否是有效的 model ID 或 provider name
    if ref in valid_bare or ref in valid_names:
        return

    # 检查 provider/model 格式
    if "/" in ref:
        prov_name, model_id = ref.split("/", 1)
        if prov_name in valid_names and model_id in valid_bare:
            return

    # 不合法 → 自动修正为第一个可用的模型 (优先新 provider)
    first = next(iter(p.models for p in providers if p.models))[0]
    sys.stderr.write(f"warning: default_model {ref!r} no longer valid; resetting to {first!r}\n")
    existing["default_model"] = first
