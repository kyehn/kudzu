- 参考 `overlays/maki/README.md` 中对 opencode 模拟的要求
- 双宿主单包：`pi.ts`（pi / node）与 `omp.ts`（omp / bun）共享 `shared.ts`
  线路逻辑（UA/headers、context 修复、网关活性门）与目录源
  （`fetchRemoteCatalog` 直连 pi.dev 注册表 + `normalizeZenModel` 形状校验）
- 只显示免费的 opencode 模型：pi.dev 注册表与 models.dev 免费且未弃用的
  条目完全一致（8 个），弃用 id（mimo-v2.5-free、deepseek-v4-flash-free）
  只可能来自过期快照，永远从注册表源消失
- pi 宿主：内置目录（`providers/all`）∪ pi.dev 源——启动时与 store 并行拉取一次，
  结果为 fresh 即**取代** `models-store.json`（store 本身就是同一份 pi.dev 载荷，
  只是更旧；仅在启动拉取失败时才按新鲜度门槛回退，Last-Modified 新于内置数据时
  按 id 覆盖，镜像 `withRemoteCatalog`）；最近一次成功结果缓存为 overlay——因为
  无头 `pi -p` 会话不会触发宿主网络刷新（allowModelNetwork 为 false），启动拉取
  保证新发布的免费模型（如 space-bunny-free）无需扩展更新即出现
- 宿主不会为被扩展覆盖的 provider 刷新缓存，因此扩展自有刷新：
  `refreshModels` 恢复宿主传入的缓存条目，并按宿主同款规则（etag 条件
  请求、4h 节流）重验证 pi.dev，成功即刷新 overlay 并经 `context.publish`
  写回缓存；失败继续提供现有 overlay
- omp 宿主：pi.dev 注册表为权威源（新免费模型进、弃用 id 不出），仅在
  pi.dev 不可达时回退 `@oh-my-pi/pi-catalog` 内置快照；两个源都过实时
  网关 id 门控（gateway 仍列出已下线 id），且 `gateByLive` 入口统一剔除
  永久退役集合（deepseek-v4-flash-free、mimo-v2.5-free、jev-1.13-free）——
  离线快照路径同样生效；注册表条目的 thinkingLevelMap 与快照条目的 thinking
  都归一为 omp 的 effort 阶梯（`THINKING_EFFORTS` 排序、不含 off）
- 无效条目跳过并警告而不拖垮整个 provider；他路付费模型静默跳过，仅可
  处理的条目告警
- 只有一个 `opencode` provider，没有重复，没有 `opencode-patched` 或类似 providers
- 使用 `ProviderModelConfig` `ProviderConfig` 等数据
- 如果 opencode tls 指纹和 bun/nodejs 类似且无检测风险，则无需对 pi 修改 tls 指纹
- 验证：`npm install && npm run typecheck && npm test`（`npm test` = node + bun
  双运行时；冒烟覆盖目录合并、新鲜度门槛、刷新重读与损坏降级、pi.dev
  启动拉取/重验证/节流/304/失败回退、omp 注册表替换（弃用 id 不出、新模型进）、
  退役 id 门控（在线 + 离线快照双路径）、effort 阶梯转换与门控）
