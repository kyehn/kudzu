"""Zen / NIM 模型 → reasonix config.toml 生成器.

唯一元数据源 = models.dev (https://models.dev/api.json); 名单来源 = 各官方
``{api}/models`` (opencode zen / NIM). 收录规则: 官方在售 ∩ models.dev 已收录
∩ status 非 deprecated ∩ 派生可聊天 ∩ (opencode 额外要求 cost 全零免费).

models.dev 字段 → reasonix 配置映射 (provider 级 + 模型级, 两表并集须覆盖
opencode/nvidia 下每一个真实出现的 key, 见 *_FIELD_* 集合与 TestFieldCoverage):

  provider id (顶层 key)  → reasonix provider 名 (opencode 按 wire 拆分时
                             后缀 "-responses", 见 build_opencode)
  provider api           → base_url; 官方名单与 chat 探活 URL 均由此派生
  provider env[0]        → api_key_env
  provider npm           → wire 默认值 (模型级 provider.npm 优先);
                           协议分支见 RESPONSES_SDK_PACKAGE
  provider name/doc      → 展示/文档, reasonix 无对应字段
  id                     → models 列表 / model_overrides key / prices key
  limit.context          → context_window (model_overrides, provider 取组内最大值)
  limit.output           → max_output_tokens (model_overrides)
  limit.input            → 忽略 (reasonix 无独立输入预算字段)
  reasoning (bool)       → reasoning_protocol="openai" (model_overrides)
  reasoning_options      → effort 值 → supported_efforts + default_effort
                           (取最高档; toggle→high; 无选项→单档high)
  reasoning_options 中 budget_tokens (含 min/max) → 忽略 (reasoning 预算
                           reasonix 不可设, 档位兜底已覆盖)
  attachment / modalities.input 含 "image" → vision=true (model_overrides)
  modalities.output 不含 "text" → 非聊天模型, 剔除
  tool_call == False     → 非 agent 模型, 剔除
  provider.npm (模型级)  → wire 协议判定 (chat / responses), 见 _wire_kind
  cost.input/output/cache_read → prices (per-model, USD); cache_write /
                           tiers / context_over_200k / input_audio 等
                           reasonix Pricing 不支持, 不入配置
  status 缺失            → 正常收录; ==deprecated → 剔除; 其他未知取值 →
                           fail-closed 报错 (models.dev 新增状态语义时大声失败)
  name/description/family/knowledge/release_date/last_updated/open_weights/
  interleaved/structured_output/temperature → 展示或运行时自适应, 无对应字段
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from reasonix_config.fetcher import fetch_models_dev, fetch_official_models
from reasonix_config.models import ModelOverride, Pricing, ProviderConfig

REASONIX_CONFIG = Path.home() / ".reasonix" / "config.toml"
MIN_CHAT_CONTEXT = 8000
# 与上游 DeepSeek-Reasonix Default().ConfigVersion 同步 (v1.33.0 = 7)。
# 钉旧值会让每次部署后的首次启动触发 ApplyUserConfigUpgradesOnStartup
# 迁移重写整个 config.toml (billing/pricing 默认值物化), 下一轮部署又
# 被钉回, 形成无谓的迁移循环。
CONFIG_VERSION = 7

# CLI 选择键 = models.dev 顶层 provider key (用户输入词汇, 非 provider 身份).
# 缺失 fail-closed (见 _provider_entry).
PROVIDER_NAMES = ("opencode", "nvidia")

# models.dev cost 单位为美元 (USD); reasonix 未显式标注币种时按本地
# display_currency 显示, 免费模型会被误读为 ¥0 的等值而非明确的 USD 0。
BILLING_CURRENCY = "USD"

# 协议知识 (opencode 客户端 SDK 包 → wire 协议), 非 provider 身份配置:
# opencode 按 models.dev provider.npm 选择 AI SDK 包: Responses SDK 包走
# OpenAI Responses (POST {base_url}/responses), 其他 (含缺省) 走与 OpenAI
# 兼容的 chat completions. provider 身份字段 (name/api/env/npm 取值) 一律
# 从 models.dev provider 条目派生, 本常量只做协议分支.
RESPONSES_SDK_PACKAGE = "@ai-sdk/openai"

# NIM 长轮询优化头. models.dev 无 headers 字段, 无数据源可派生, 显式声明
# (NIM 文档行为); 与 provider 身份无关.
NIM_EXTRA_HEADERS = {"NVCF-POLL-SECONDS": "3600"}

# Zen 匿名凭据 (opencode 文档行为, 无 key 即可用免费层; reasonix 仍需发送
# Authorization 头, 故以 "public" 占位). 占位键名从 provider env[0] 派生,
# 只给 opencode 补 (见 __main__); nvidia 缺 key 必须 fail-closed, 永不写假值.
ZEN_ANONYMOUS_CREDENTIAL = "public"

# models.dev 现实中出现的 status 取值 (实测 2026-09: 仅 missing/deprecated).
# 未知取值 fail-closed, 见 _check_status.
KNOWN_STATUSES: frozenset[str | None] = frozenset({None, "deprecated"})

# models.dev 字段级覆盖率审计. 两集合并集必须覆盖 opencode/nvidia 下每一个
# 真实出现的 key, 否则 TestFieldCoverage 会失败——新增字段须在此显式归类
# (handled 或 ignored), 不允许静默遗漏.
MODEL_FIELD_HANDLED: frozenset[str] = frozenset(
    {
        "id",  # 用作模型 key, 不参与覆盖映射
        "limit",  # context/output -> context_window/max_output_tokens (input 忽略)
        "cost",  # input/output/cache_read -> Pricing (其余分项忽略)
        "modalities",  # output 含 text 决定可否作聊天模型; input 含 image -> vision
        "attachment",  # True -> vision
        "reasoning",  # True -> reasoning_protocol
        "reasoning_options",  # effort -> supported_efforts/default_effort (budget_tokens 忽略)
        "status",  # deprecated -> 剔除, 未知 -> fail-closed
        "tool_call",  # False -> 非 agent 模型, 剔除
        "provider",  # 模型级 npm -> wire 协议判定, 见 _wire_kind
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
        "id",  # 顶层 key 即 reasonix provider 名 (按 wire 拆分时加后缀)
        "api",  # -> base_url; 官方名单 / 探活用 URL 均由此派生
        "env",  # env[0] -> api_key_env
        "models",  # -> models / model_overrides / prices
        "npm",  # wire 默认值 (模型级 provider.npm 优先), 见 _wire_kind
    }
)
PROVIDER_FIELD_IGNORED: frozenset[str] = frozenset(
    {
        "name",  # 展示名, reasonix 无展示字段
        "doc",  # 文档链接
    }
)


def _provider_entry(md_data: dict[str, Any], pid: str) -> dict[str, Any]:
    """取 models.dev provider 条目并校验必需字段 (缺失 fail-closed).

    必需: api / env(非空) / models. name/npm 缺失仅告警? 不——同样
    fail-closed: provider 条目形态漂移时静默生成等于编造配置.
    """
    entry = md_data.get(pid)
    if not isinstance(entry, dict):
        msg = f"models.dev has no {pid!r} provider; refusing to guess provider identity"
        raise SystemExit(msg)
    for key in ("api", "env", "models", "name", "npm"):
        if not entry.get(key):
            msg = f"models.dev provider {pid!r} has no usable {key!r}; refusing to guess"
            raise SystemExit(msg)
    return entry


def _check_status(mid: str, m: dict[str, Any]) -> bool:
    """True=收录, False=剔除 (deprecated); 未知 status 取值 fail-closed."""
    status = m.get("status")
    if status not in KNOWN_STATUSES:
        msg = f"models.dev model {mid!r} has unknown status {status!r}; refusing to guess"
        raise SystemExit(msg)
    return status != "deprecated"


def _is_free(m: dict[str, Any]) -> bool:
    """免费判定: cost.input/output 必须显式为零.

    缺 cost 字段或缺分项一律不算免费 (paid-leak 方向 fail-closed:
    models.dev 新增付费模型若漏标 cost, 误收进免费配置比漏收更糟).
    """
    cost = m.get("cost")
    if not isinstance(cost, dict):
        return False
    return cost.get("input") == 0 and cost.get("output") == 0


def _wire_kind(m: dict[str, Any], default_npm: str) -> str:
    """models.dev npm → reasonix kind (openai | responses).

    模型级 provider.npm 优先, 缺失用 provider 级 npm; 等于 RESPONSES_SDK_PACKAGE
    走 Responses, 其余 (含 openai-compatible 与 anthropic/google 族) 走与
    OpenAI 兼容的 chat completions (zen 网关负责翻译; 免费集实测无
    anthropic/google 族, 该分支天然休眠).
    """
    npm = ((m.get("provider") or {}).get("npm")) or default_npm
    return "responses" if npm == RESPONSES_SDK_PACKAGE else "openai"


def _resolve_efforts(m: dict[str, Any]) -> tuple[list[str], str]:
    """reasoning_options → (supported_efforts, default_effort).

    reasoning=True 的模型必须声明 supported_efforts, 否则 reasonix 将其视为
    不可调努力等级. effort 取 values 全集, 默认取末个非 none 值; toggle 兜底
    high; 无选项只声明 ["high"] (注: 无元数据不发明梯度——误档由 reasonix
    NormalizeEffort 及时报错而非静默接受; 未来若有 responses 路径且无
    options 的免费新模型,需显式复核 high 是否合法,不可默认沿用本兜底;
    opencode chat wire 根本不发送
    reasoning 字段, 该元数据对 chat 模型仅信息性; responses 模型如 spark 在
    models.dev 均有完整 effort 表, high 单档只是从未命中的安全缺省.)
    """
    for opt in m.get("reasoning_options", []):
        if isinstance(opt, dict) and opt.get("type") == "effort":
            values = [v for v in opt.get("values", []) if v is not None]
            if values:
                non_none = [v for v in values if v != "none"]
                return values, (non_none[-1] if non_none else values[-1])
    if any(
        isinstance(o, dict) and o.get("type") == "toggle" for o in m.get("reasoning_options", [])
    ):
        return ["high"], "high"
    return ["high"], "high"


def _build_override(m: dict[str, Any]) -> dict[str, Any]:
    """从 models.dev 元数据构建 model_overrides 条目.

    输出字段名与 reasonix ProviderModelOverride 的 toml tag 严格一致:
    context_window / max_output_tokens / reasoning_protocol / supported_efforts /
    default_effort / vision. (thinking 仅存在于 ProviderEntry 级, 不放这里.)
    """
    override: dict[str, Any] = {}
    limit = m.get("limit") or {}
    if limit.get("context"):
        override["context_window"] = limit["context"]
    if limit.get("output"):
        override["max_output_tokens"] = limit["output"]
    if m.get("reasoning", True):
        override["reasoning_protocol"] = "openai"
        supported, default = _resolve_efforts(m)
        override["supported_efforts"] = supported
        override["default_effort"] = default
    modalities_input = (m.get("modalities") or {}).get("input", [])
    if m.get("attachment") or ("image" in (modalities_input or [])):
        override["vision"] = True
    return override


def _price_of(m: dict[str, Any]) -> Pricing | None:
    """从 models.dev cost 字段解析单模型价格 (落到 provider.prices[mid]).

    映射: cost.input -> input, cost.output -> output, cost.cache_read -> cache_hit;
    cache_write / tiers / context_over_200k / input_audio 等其余分项 reasonix
    Pricing 无对应字段, 忽略. 单位美元, 显式标 USD (见 Pricing.currency).
    数值合法性交由 pydantic 校验. 三项全零视为免费, 返回 None 不入表.
    """
    cost = m.get("cost") or {}
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

    纯派生检查, 无名字硬编码:
    - limit.context >= MIN_CHAT_CONTEXT (token budget large enough to converse)
    - modalities.output must contain "text": pure image/video/audio generators
      cannot answer in text, so they must be pruned here.
    - tool_call must not be False: an agent requires tool calling; entries with
      tool_call=True or a missing key stay (legacy entries omit the field), only
      an explicit False is pruned.
    """
    limit = mdata.get("limit") or {}
    if (limit.get("context", 0) or 0) < MIN_CHAT_CONTEXT:
        return False
    modalities = mdata.get("modalities", {}) or {}
    if (modalities.get("output") or []) and "text" not in modalities["output"]:
        return False
    # 仅显式 False 剔除 (None/缺失/True 保留): agent 可执行性判定.
    return mdata.get("tool_call") is not False


def _official_ids(official_data: dict[str, Any], api_url: str) -> set[str]:
    """官方名单 {"data": [{"id"}]} → id 集合 (形态不符 fail-closed)."""
    data = official_data.get("data")
    if not isinstance(data, list):
        msg = f"official model list at {api_url} has unexpected shape (want {{'data': [...]}})"
        raise SystemExit(msg)
    ids: set[str] = set()
    for entry in data:
        mid = entry.get("id") if isinstance(entry, dict) else None
        if not mid:
            msg = f"official model list at {api_url} has entry without id: {entry!r}"
            raise SystemExit(msg)
        ids.add(mid)
    return ids


def _build_wire_provider(
    name: str,
    kind: str,
    entries: list[tuple[str, dict[str, Any]]],
    entry: dict[str, Any],
) -> ProviderConfig | None:
    """组装单个 wire 协议的 provider (models/overrides/价格/default).

    身份字段全部取自 models.dev provider 条目: base_url=api, api_key_env=env[0].
    """
    if not entries:
        return None

    models_list: list[str] = []
    model_prices: dict[str, Pricing] = {}
    model_overrides: dict[str, ModelOverride] = {}
    max_context = 0

    for mid, m in entries:
        models_list.append(mid)
        max_context = max(max_context, (m.get("limit") or {}).get("context", 0))
        price = _price_of(m)
        if price:
            model_prices[mid] = price
        override = _build_override(m)
        if override:
            model_overrides[mid] = ModelOverride(**override)

    return ProviderConfig(
        name=name,
        kind=kind,
        base_url=entry["api"],
        models=models_list,
        default=models_list[0],
        api_key_env=entry["env"][0],
        context_window=max_context,
        prices=model_prices or None,
        model_overrides=model_overrides or None,
        billing_currency=BILLING_CURRENCY,
        # Responses 网关无状态: 不续接 previous_response_id
        responses_mode="stateless" if kind == "responses" else None,
        headers=None,
    )


def build_opencode(
    pid: str,
    md_data: dict[str, Any],
    official_data: dict[str, Any],
    api_url: str,
) -> list[ProviderConfig]:
    """Zen 免费模型, 按 wire 协议拆分为 provider 列表.

    收录 = 官方在售 ∩ models.dev 已收录 ∩ 非 deprecated ∩ cost 全零 ∩ 可聊天.
    官方有而 models.dev 未收录的 id 一律排除: 条目缺失无法证明免费与能力,
    误收会导致无元数据模型进入配置甚至成为 default. wire 拆分见 _wire_kind
    (Responses 模型走 /responses, chat/completions 对它返回 HTTP 500).
    """
    entry = _provider_entry(md_data, pid)
    models_raw = entry["models"]
    default_npm = entry["npm"]
    wanted = _official_ids(official_data, api_url)

    by_wire: dict[str, list[tuple[str, dict[str, Any]]]] = {"openai": [], "responses": []}
    for mid in sorted(wanted):
        m = models_raw.get(mid)
        if m is None:
            continue  # 官方有而 models.dev 未收录: 无法证明免费与能力, 排除
        if not _check_status(mid, m):
            continue
        if not _is_free(m):
            continue
        if not _is_chat_model(mid, m):
            continue
        by_wire[_wire_kind(m, default_npm)].append((mid, m))

    providers: list[ProviderConfig] = []
    for kind in ("openai", "responses"):
        # 拆分名由 key 派生 (无字面量): 主 provider 保持原 key.
        name = pid if kind == "openai" else f"{pid}-responses"
        cfg = _build_wire_provider(name, kind, by_wire[kind], entry)
        if cfg is not None:
            providers.append(cfg)

    if not providers:
        msg = f"No free {pid} models found"
        raise SystemExit(msg)
    return providers


def build_nvidia(
    pid: str,
    md_data: dict[str, Any],
    official_data: dict[str, Any],
    api_url: str,
    dead: set[str] | None = None,
) -> ProviderConfig:
    """NVIDIA NIM 聊天模型: 官方在售 ∩ models.dev 非 deprecated ∩ 可聊天.

    dead: 探活确认不可用 (NIM 404) 的模型 id, 剔除 (见 probe_nvidia_live;
    超时等含混结果永不进入 dead, 宁可保留).
    headers: NIM 长轮询优化头, models.dev 无对应字段, 见 NIM_EXTRA_HEADERS.
    """
    entry = _provider_entry(md_data, pid)
    models_raw = entry["models"]
    wanted = _official_ids(official_data, api_url)
    dead = dead or set()

    models_list: list[str] = []
    model_prices: dict[str, Pricing] = {}
    model_overrides: dict[str, ModelOverride] = {}
    max_context = 0

    for mid in sorted(wanted):
        m = models_raw.get(mid)
        if m is None:
            continue  # 官方有而 models.dev 未收录: 无元数据, 排除
        if not _check_status(mid, m):
            continue
        if mid in dead:
            continue  # 探活 404: NIM 侧已下架
        if not _is_chat_model(mid, m):
            continue
        models_list.append(mid)
        max_context = max(max_context, (m.get("limit") or {}).get("context", 0))
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
        name=pid,
        kind="openai",
        base_url=entry["api"],
        models=models_list,
        default=models_list[0],
        api_key_env=entry["env"][0],
        context_window=max_context,
        prices=model_prices or None,
        model_overrides=model_overrides or None,
        billing_currency=BILLING_CURRENCY,
        headers=dict(NIM_EXTRA_HEADERS),
    )


def _fetch_official_list(entry: dict[str, Any], pid: str) -> dict[str, Any]:
    """官方名单, 无认证优先, 401/403 类失败时带 key 重试一次.

    哪家要认证不写死: zen 公开名单直接成功; NIM 无 key 请求被拒后
    取 entry env[0] 的环境变量重试, 仍无 key 则 fail-closed (不猜名单,
    报错点名缺的键).
    无 key 时禁用缓存读取: 缓存可能是之前带 key 拉的 NIM 名单,
    读它等于绕过 key 门 (keyless 运行必须走公益网关实时名单).
    """
    env_name = entry["env"][0]
    key = os.environ.get(env_name, "").strip()
    if not key:
        # 无 key: 缓存不可信 (可能是带 key 拉的旧名单), 直接实时拉匿名名单;
        # 失败即 fail-closed, 报错点名缺的键.
        try:
            return fetch_official_models(entry, pid, use_cache=False)
        except SystemExit:
            msg = f"official model list for {pid!r} needs {env_name}; refusing to guess"
            raise SystemExit(msg) from None
    try:
        return fetch_official_models(entry, pid)
    except SystemExit:
        return fetch_official_models(entry, pid, key)


def build_all(
    providers_filter: list[str] | None = None,
    dead: dict[str, set[str]] | None = None,
    md_data: dict[str, Any] | None = None,
    official: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[ProviderConfig], list[str]]:
    """dead: 按 provider 名索引的探活证伪名单 (只删探活 404 的).

    md_data / official 为空时实时拉取 (测试可注入 hermetic 夹具).
    官方名单缺失且无法拉取时 fail-closed (fetch_official_models 抛 SystemExit):
    名单是收录交集的一边, 猜名单等于编造配置.
    返回 (providers, errors): 单家失败只记 errors, 不丢另一家的成功构建;
    调用方先写成功部分, 再凭 errors 非零退出 (见 __main__.main).
    """
    wanted = set(providers_filter) if providers_filter is not None else set(PROVIDER_NAMES)
    unknown = wanted - set(PROVIDER_NAMES)
    if unknown:
        msg = f"unknown provider(s) {sorted(unknown)}; want one of {list(PROVIDER_NAMES)}"
        raise SystemExit(msg)
    md_data = fetch_models_dev() if md_data is None else md_data
    official = {} if official is None else official
    providers: list[ProviderConfig] = []
    errors: list[str] = []
    if "opencode" in wanted:
        try:
            entry = _provider_entry(md_data, "opencode")
            official_data = official.get("opencode")
            if official_data is None:
                official_data = _fetch_official_list(entry, "opencode")
            providers.extend(
                build_opencode(
                    "opencode", md_data, official_data, f"{entry['api'].rstrip('/')}/models"
                )
            )
        except SystemExit as exc:
            # 按 provider 隔离: 一家元数据/名单出问题, 不丢另一家的更新;
            # 错误汇总后由调用方先写成功部分再非零退出 (见 __main__).
            errors.append(str(exc))
    if "nvidia" in wanted:
        try:
            entry = _provider_entry(md_data, "nvidia")
            official_data = official.get("nvidia")
            if official_data is None:
                official_data = _fetch_official_list(entry, "nvidia")
            providers.append(
                build_nvidia(
                    "nvidia",
                    md_data,
                    official_data,
                    f"{entry['api'].rstrip('/')}/models",
                    (dead or {}).get("nvidia"),
                )
            )
        except SystemExit as exc:
            errors.append(str(exc))
    return providers, errors


def ensure_env_placeholder(api_key_env: str) -> None:
    """确保 ``<api_key_env>=public`` 存在于 ``~/.reasonix/.env`` (zen 匿名凭据).

    键名由调用方从 models.dev provider env[0] 传入 (本函数内无字面量);
    值 "public" 为 zen 文档化的匿名凭据, 见 ZEN_ANONYMOUS_CREDENTIAL.
    已有值原样保留 (用户 key 走付费/独立配额, 不可静默降级); 重复行折叠.
    """
    env_path = REASONIX_CONFIG.parent / ".env"
    prefix = f"{api_key_env}="

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
            new_lines.append(f"{prefix}{ZEN_ANONYMOUS_CREDENTIAL}")
            new_lines.append("")
        env_path.write_text("\n".join(new_lines) + "\n")
        env_path.chmod(0o600)
    else:
        env_path.write_text(f"{prefix}{ZEN_ANONYMOUS_CREDENTIAL}\n")
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

    _run_reasonix_doctor()

    return config_path


def _repair_default_model(
    existing: dict[str, Any],
    providers: list[ProviderConfig],
) -> None:
    """Own ``default_model``: write it when missing, reset when invalid.

    生成器拥有该字段的派生权 (nix 只留初始兜底): 缺失时写入首个新
    provider 的首个模型; 已有值仅在非法时修正, 永不覆盖用户选择.
    有效引用集合 = 新 provider 的模型/名字 + 保留的旧 provider 的模型/名字
    (default_model 可能指向未参与本次更新的其他 provider, 不能误判为无效).
    """
    if not providers or not providers[0].models:
        return
    first = providers[0].models[0]
    ref = existing.get("default_model")
    if ref is None:
        sys.stderr.write(f"warning: default_model missing; setting to {first!r}\n")
        existing["default_model"] = first
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

    # 不合法 → 自动修正为第一个可用的模型 (优先新 provider, 复用函数入口的 first)
    sys.stderr.write(f"warning: default_model {ref!r} no longer valid; resetting to {first!r}\n")
    existing["default_model"] = first
