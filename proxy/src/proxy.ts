import { readFile, writeFile, mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { createServer, IncomingMessage, ServerResponse } from "node:http";
import { request as httpsRequest } from "node:https";
import { parse as parseToml, stringify as stringifyToml } from "@iarna/toml";
import { parse as parseJson, stringify as stringifyJson } from "comment-json";

import { sessionId, requestId, projectId } from "./identifier.js";
import { 
  fetchUpstreamModelIds, 
  fetchModelsDevInfo, 
  isFreeModelId, 
  isDeprecated,
  ModelsDevModelInfo,
  UpstreamModelListResponse
} from "./models.js";

const PORT = 3456;
const UPSTREAM = "https://opencode.ai/zen";
const UPSTREAM_URL = new URL(UPSTREAM);

const SESSION_ID = sessionId();
const PROJECT_ID = projectId(process.cwd());

function opencodeHeaders(): Record<string, string> {
  return {
    "User-Agent": "opencode/1.17.15/cli",
    "x-opencode-client": "cli",
    "x-opencode-session": SESSION_ID,
    "x-opencode-project": PROJECT_ID,
    "x-opencode-request": requestId(),
    "Authorization": "Bearer public",
  };
}

function detectAgent(ua: string | undefined): "droid" | "reasonix" | "dirac" | "unknown" {
  if (!ua) return "unknown";
  const lower = ua.toLowerCase();
  if (lower.startsWith("dirac")) return "dirac";
  if (lower.includes("go-http-client") || lower.includes("reasonix") || lower.includes("deepseek-reasonix") || lower.includes("openai-js") || lower.includes("openai_node")) return "reasonix";
  if (lower.includes("droid") || lower.includes("factory")) return "droid";
  return "unknown";
}

function transformHeaders(agent: string, headers: Record<string, string | string[] | undefined>): Record<string, string> {
  const out: Record<string, string> = {};
  const skip = new Set(["host", "connection", "keep-alive", "proxy-connection", "transfer-encoding", "authorization", "x-api-key", "api-key", "content-length"]);

  for (const [k, v] of Object.entries(headers)) {
    if (!skip.has(k.toLowerCase()) && v !== undefined) {
      out[k] = Array.isArray(v) ? v.join(", ") : v;
    }
  }

  Object.assign(out, opencodeHeaders());
  return out;
}

async function proxyRequest(req: IncomingMessage, res: ServerResponse, body: string): Promise<void> {
  const agent = detectAgent(req.headers["user-agent"]);
  const headers = transformHeaders(agent, req.headers as Record<string, string>);

  const isChat = req.url?.includes("/chat/completions") || req.url?.includes("/completions");
  const path = "/zen" + (req.url ?? "/");

  const options = {
    hostname: UPSTREAM_URL.hostname,
    port: UPSTREAM_URL.port || 443,
    path,
    method: req.method,
    headers,
    timeout: 300_000,
  };

  const proxyReq = httpsRequest(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode!, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on("error", (e) => {
    if (!res.headersSent) {
      res.writeHead(502, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: { message: "Upstream error: " + e.message, type: "proxy_error" } }));
    }
  });

  proxyReq.write(body);
  proxyReq.end();
}

async function serveModels(res: ServerResponse, models: string[], modelsDev: Record<string, ModelsDevModelInfo>): Promise<void> {
  const data = models
    .filter(isFreeModelId)
    .map((id) => {
      const info = modelsDev[id] || {};
      const ctx = info.limit?.context ?? 128_000;
      const out = info.limit?.output ?? 4_096;
      return {
        id,
        object: "model",
        created: Math.floor(Date.now() / 1000),
        owned_by: "opencode",
        context_window: ctx,
        max_output_tokens: out,
      };
    });
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ object: "list", data }));
}

async function handleRequest(req: IncomingMessage, res: ServerResponse, state: { modelIds: string[]; modelsDevInfo: Record<string, ModelsDevModelInfo> }): Promise<void> {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", session: SESSION_ID, project: PROJECT_ID }));
    return;
  }

  if (req.url === "/v1/models" && req.method === "GET") {
    await serveModels(res, state.modelIds, state.modelsDevInfo);
    return;
  }

  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk);
  const body = Buffer.concat(chunks).toString();

  await proxyRequest(req, res, body);
}

const HOME = homedir();

async function safeReadJson(path: string): Promise<any> {
  try { return parseJson(await readFile(path, "utf8"), null, true); } catch { return null; }
}

async function safeReadToml(path: string): Promise<any> {
  try { return parseToml(await readFile(path, "utf8")); } catch { return null; }
}

async function ensureDir(path: string): Promise<void> {
  await mkdir(path, { recursive: true });
}

async function setupDroid(port: number, models: string[], modelsDev: Record<string, ModelsDevModelInfo>): Promise<void> {
  const cfgPath = join(HOME, ".factory", "settings.json");
  await ensureDir(join(HOME, ".factory"));
  const existing = await safeReadJson(cfgPath) || {};
  if (!existing.customModels) existing.customModels = [];

  const freeModels = models.filter(isFreeModelId);
  const modelSet = new Set(existing.customModels.filter((m: any) => m.__opencode_zen_proxy__).map((m: any) => m.model));

  for (const id of freeModels) {
    const info = modelsDev[id] || {};
    const entry = {
      __opencode_zen_proxy__: true,
      model: id,
      displayName: id,
      baseUrl: `http://127.0.0.1:${port}/v1`,
      apiKey: "public",
      provider: "generic-chat-completion-api",
      maxOutputTokens: info.limit?.output ?? 4096,
    };
    if (modelSet.has(id)) {
      const idx = existing.customModels.findIndex((m: any) => m.model === id && m.__opencode_zen_proxy__);
      if (idx >= 0) existing.customModels[idx] = entry;
    } else {
      existing.customModels.push(entry);
    }
  }

  await writeFile(cfgPath, stringifyJson(existing, null, 2) + "\n");
}

async function setupReasonix(port: number, models: string[], modelsDev: Record<string, ModelsDevModelInfo>): Promise<void> {
  const cfgPath = join(HOME, ".reasonix", "config.toml");
  await ensureDir(join(HOME, ".reasonix"));
  const existing = await safeReadToml(cfgPath) || {};
  if (!Array.isArray(existing.providers)) existing.providers = [];

  const freeModels = models.filter(isFreeModelId);
  existing.providers = existing.providers.filter((p: any) => !p._opencode_zen_proxy);

  for (const id of freeModels) {
    const info = modelsDev[id] || {};
    existing.providers.push({
      _opencode_zen_proxy: true,
      name: id,
      kind: "openai",
      base_url: `http://127.0.0.1:${port}/v1`,
      api_key: "public",
      model: id,
      context_window: info.limit?.context ?? 128_000,
    });
  }

  await writeFile(cfgPath, stringifyToml(existing));
}

async function setupDirac(port: number, models: string[], _modelsDev: Record<string, ModelsDevModelInfo>): Promise<void> {
  const cfgDir = join(HOME, ".config", "dirac");
  await ensureDir(cfgDir);
  const envPath = join(cfgDir, "proxy.env");
  const freeModels = models.filter(isFreeModelId);
  const content = [
    "# opencode-zen proxy env — source this before running dirac",
    "# Usage: source " + envPath + " && dirac",
    `export OPENAI_API_BASE="http://127.0.0.1:${port}/v1"`,
    `export OPENAI_API_KEY="public"`,
    `export OPENAI_BASE_URL="http://127.0.0.1:${port}/v1"`,
    `# Default model (override with: dirac -m <model>)`,
    `export DIRAC_MODEL="${freeModels[0] || ""}"`,
  ].join("\n") + "\n";
  await writeFile(envPath, content);
}

async function loadBootstrapState(): Promise<{ modelIds: string[]; modelsDevInfo: Record<string, ModelsDevModelInfo> }> {
  const [upstreamModelIds, modelsDevInfo] = await Promise.all([
    fetchUpstreamModelIds(UPSTREAM),
    fetchModelsDevInfo(),
  ]);

  const upstreamSet = new Set(upstreamModelIds);
  const modelIds = [...upstreamSet]
    .filter(isFreeModelId)
    .filter((id) => !isDeprecated(modelsDevInfo[id]));

  return { modelIds, modelsDevInfo };
}

export function startProxy(port: number = PORT): ReturnType<typeof createServer> {
  let state: { modelIds: string[]; modelsDevInfo: Record<string, ModelsDevModelInfo> };
  
  const server = createServer(async (req, res) => {
    try {
      if (!state) {
        state = await loadBootstrapState();
      }
      
      if (req.url === "/health") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "ok", session: SESSION_ID, project: PROJECT_ID }));
        return;
      }

      if (req.url === "/v1/models" && req.method === "GET") {
        await serveModels(res, state.modelIds, state.modelsDevInfo);
        return;
      }

      const chunks: Buffer[] = [];
      for await (const chunk of req) chunks.push(chunk);
      const body = Buffer.concat(chunks).toString();

      await proxyRequest(req, res, body);
    } catch (e) {
      console.error("Request error:", e);
      if (!res.headersSent) {
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: { message: "Internal error", type: "proxy_error" } }));
      }
    }
  });

  const shutdown = () => {
    console.log("\n⏹️  Shutting down...");
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(1), 5000);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  server.listen(port, "127.0.0.1", () => {
    console.log(`\n🚀 opencode-zen proxy listening on http://127.0.0.1:${port}`);
    console.log(`   Session: ${SESSION_ID}`);
    console.log(`   Project: ${PROJECT_ID}`);
    console.log(`   Upstream: ${UPSTREAM}`);
    console.log(`\n   Health:  curl http://127.0.0.1:${port}/health`);
    console.log(`   Models:  curl http://127.0.0.1:${port}/v1/models`);
    console.log(`   Chat:    curl -X POST http://127.0.0.1:${port}/v1/chat/completions \\`);
    console.log(`              -H "Content-Type: application/json" \\`);
    console.log(`              -d '{"model":"deepseek-v4-flash-free","messages":[{"role":"user","content":"Say PONG"}]}'`);
  });

  setInterval(async () => {
    try {
      const fresh = await loadBootstrapState();
      if (state) {
        state.modelIds = fresh.modelIds;
        state.modelsDevInfo = fresh.modelsDevInfo;
      }
      console.log(`🔄 Refreshed: ${fresh.modelIds.length} free models`);
    } catch (e) {
      console.error("Refresh failed:", e);
    }
  }, 60 * 60 * 1000);

  return server;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  startProxy();
}

export { setupDroid, setupReasonix, setupDirac, loadBootstrapState };