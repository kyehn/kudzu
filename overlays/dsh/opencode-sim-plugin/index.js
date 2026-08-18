// OpenCode 模拟装配插件（cordis，dsh loader 标准 apply/inject 格式）。
//
// 职责（全部为运行时装配，nix 配置零模型数据硬编码）：
//   1. 向 `llm-pi-ai` settings namespace update 一个 openai provider：
//      路由到 opencode zen 网关，并声明 `x-opencode-client`/`x-opencode-project`
//      trigger headers —— 注入层（opencode-sim.mjs）检测到即装配与
//      overlays/reasonix/alignment.patch 同源的完整 opencode 客户端特征
//      （权威 UA/Accept/Accept-Encoding、动态 ses_/msg_ id、TLS 指纹参数）。
//   2. 将默认模型设为该 provider（等价 web Models 页的默认模型选择）。
//
// 时序：llm-pi-ai 等 `llm` 服务激活后才通过 installSettingsSection 注册
// settings namespace，与我们的 apply（等 `settings` 激活）并行竞争；因此
// 装配协程先轮询等待 namespace 注册完成，再执行 update —— 与手写
// settings.yaml 完全等价（后者正是 web Models 页的写入路径），且经
// llm-pi-ai 的 onChange 热重载路由，无竞态（首个请求远晚于装配）。
//
// 可复现性：本文件与模拟层均版本化于仓库，dsh-config overlay 重建即得
// 相同装配，不依赖手工编辑。

const OPENCODE_PROVIDER_ID = "openai";
const OPENCODE_API_BASE_URL =
  process.env.OPENCODE_BASE_URL ?? "https://api.opencode.ai/zen/v1";
export const OPENCODE_DEFAULT_MODEL =
  process.env.OPENCODE_DEFAULT_MODEL ?? "deepseek-v4-flash-free";

export const name = "opencode-sim";
export const inject = ["settings"];

export function apply(ctx) {
  void assemble(ctx).catch((error) =>
    ctx.logger.error("opencode-sim: %s", error),
  );
}

/**
 * 装配协程：等注入方 namespace 注册完成后写入 provider 路由与默认模型。
 * @param ctx - loader 树上下文（settings 服务已激活）。
 */
async function assemble(ctx) {
  await waitForNamespaces(ctx.settings, ["llm-pi-ai", "agent-default-model"]);
  await ctx.settings.update("llm-pi-ai", {
    providers: {
      [OPENCODE_PROVIDER_ID]: {
        apiKeyEnv: "OPENCODE_API_KEY",
        api: "openai-completions",
        baseURL: OPENCODE_API_BASE_URL,
        // 触发注入层的 opencode 特征装配（值本身与小写 wire 名一致）
        headers: {
          "x-opencode-client": "cli",
          "x-opencode-project": "global",
        },
        models: [{ id: OPENCODE_DEFAULT_MODEL }],
      },
    },
  });

  const defaultModel = await ctx.get("agentDefaultModel");
  if (defaultModel) {
    await defaultModel.saveSelection({
      provider: OPENCODE_PROVIDER_ID,
      model: OPENCODE_DEFAULT_MODEL,
    });
  }
}

/**
 * 轮询等待 settings namespace 注册（llm-pi-ai 的 installSettingsSection 在
 * `llm` 服务激活后异步注册，无注册完成事件可监听）。
 * @param settings - settings 服务实例。
 * @param namespaces - 需等待注册的 namespace 列表。
 */
function waitForNamespaces(settings, namespaces) {
  return Promise.all(
    namespaces.map(
      (ns) =>
        new Promise((resolve) => {
          const poll = () => {
            if (settings.registrations.has(ns)) return resolve(void 0);
            setTimeout(poll, 25);
          };
          poll();
        }),
    ),
  );
}
