#!/usr/bin/env node

// ─── opencode-zen proxy ─────────────────────────────────────────────
// Local HTTP proxy that injects opencode-compatible x-opencode-*
// headers, enriches model metadata via models.dev, and forwards
// requests to the upstream opencode API.
//
// Agent-aware: detects dirac / Reasonix / Droid from User-Agent
// and adapts headers + request body accordingly.
//
// Zero-dep proxy core.  Config writing uses:
//   comment-json  (Droid  — preserves comments in settings.json)
//   @iarna/toml   (Reasonix — proper TOML array-of-tables)
//   env file      (dirac — OPENAI_API_BASE / OPENAI_API_KEY / CUSTOM_HEADERS)
//
// Usage:
//   node proxy.mjs                         # start proxy on :3456
//   node proxy.mjs --port 4000             # custom port
//   node proxy.mjs --setup                 # write agent configs only
//   node proxy.mjs --setup --agents droid  # write only droid config
//   node proxy.mjs --help                  # show help
// ─────────────────────────────────────────────────────────────────────

import http from "node:http";
import https from "node:https";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { parse as parseToml, stringify as stringifyToml } from "@iarna/toml";
import { parse as parseJson, stringify as stringifyJson } from "comment-json";

// ─── CLI Parsing (zero-dep, ~40 lines) ──────────────────────────────

const HELP = `opencode-zen-proxy

Usage:
  node proxy.mjs [options]

Options:
  --port <n>         Listen port                 (default: 3456)
  --upstream <url>   Upstream API base URL       (default: https://opencode.ai/zen)
  --setup            Write agent config files and exit
  --agents <list>    Comma-separated agents for --setup
                     (default: droid,reasonix,dirac)
  --help             Show this help

Examples:
  node proxy.mjs                          # start on port 3456
  node proxy.mjs --port 8080              # start on port 8080
  node proxy.mjs --setup --agents droid   # write only droid config
  node proxy.mjs --setup                  # write all agent configs
`;

function parseArgs(argv) {
  const args = argv.slice(2);
  const opts = { port: 3456, upstream: "https://opencode.ai/zen", setup: false, agents: ["droid", "reasonix", "dirac"], help: false };
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === "--help" || a === "-h") { opts.help = true; }
    else if (a === "--port" && args[i + 1]) { opts.port = parseInt(args[++i], 10); }
    else if (a === "--upstream" && args[i + 1]) { opts.upstream = args[++i]; }
    else if (a === "--setup") { opts.setup = true; }
    else if (a === "--agents" && args[i + 1]) { opts.agents = args[++i].split(",").map(s => s.trim().toLowerCase()); }
  }
  return opts;
}

const CLI = parseArgs(process.argv);
if (CLI.help) { console.log(HELP); process.exit(0); }

// ─── Identifier helpers (match real opencode format) ─────────────────

const B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

let _counter = 0;
let _lastTs = 0;

function descendingId() {
  const now = Date.now();
  if (now !== _lastTs) { _lastTs = now; _counter = 0; }
  _counter++;
  const current = BigInt(now) * 0x1000n + BigInt(_counter);
  const value = ~current;
  const time = Array.from({ length: 6 }, (_, i) =>
    Number((value >> BigInt(40 - 8 * i)) & 0xffn).toString(16).padStart(2, "0"),
  ).join("");
  const bytes = crypto.randomBytes(14);
  const random = Array.from(bytes, (b) => B62[b % 62]).join("");
  return time + random;
}

function deriveProjectId() {
  const cwd = process.cwd();
  const hash = crypto.createHash("sha256").update(cwd).digest();
  let num = BigInt("0x" + hash.subarray(0, 8).toString("hex"));
  let result = "";
  while (num > 0n && result.length < 26) {
    result = B62[Number(num % 62n)] + result;
    num /= 62n;
  }
  return result.padEnd(26, "0").slice(0, 26);
}

// ─── State ───────────────────────────────────────────────────────────

let upstreamModelIds = [];
let upstreamModelsDev = {};

// ─── Constants ───────────────────────────────────────────────────────

const UPSTREAM = CLI.upstream;
const UPSTREAM_URL = new URL(UPSTREAM);
const SESSION_ID = "ses_" + descendingId();
const PROJECT_ID = "prj_" + deriveProjectId();
const MODEL_LIST_CACHE = 3600_000; // 1 hour
const EFFORT_ORDER = ["minimal", "low", "medium", "high", "xhigh", "max"];

// ─── Agent detection ────────────────────────────────────────────────

function detectAgent(ua) {
  if (!ua) return "unknown";
  const lower = ua.toLowerCase();
  if (lower.startsWith("dirac")) return "dirac";
  // Reasonix uses Go HTTP client or OpenAI SDK or its own User-Agent
  if (lower.includes("go-http-client") || lower.includes("reasonix") || lower.includes("deepseek-reasonix") || lower.includes("openai-js") || lower.includes("openai_node")) return "reasonix";
  if (lower.includes("droid") || lower.includes("factory")) return "droid";
  return "unknown";
}

// ─── opencode-compatible request headers ─────────────────────────────

function opencodeHeaders() {
  return {
    "User-Agent": "opencode/1.17.15/cli",
    "x-opencode-client": "cli",
    "x-opencode-session": SESSION_ID,
    "x-opencode-project": PROJECT_ID,
    "x-opencode-request": "msg_" + descendingId(),
    "Authorization": "Bearer public",
  };
}

// ─── models.dev helpers ──────────────────────────────────────────────

async function httpGet(url) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith("https") ? https : http;
    const req = mod.get(url, { timeout: 15_000 }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return httpGet(res.headers.location).then(resolve, reject);
      }
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => {
        try { resolve(JSON.parse(Buffer.concat(chunks).toString())); }
        catch { reject(new Error("JSON parse error from " + url)); }
      });
      res.on("error", reject);
    }).on("error", reject);
  });
}

async function fetchUpstreamModelIds() {
  try {
    const r = await httpGet(UPSTREAM + "/v1/models");
    const ids = (r.data || []).map((m) => m.id).filter(Boolean);
    if (ids.length > 0) upstreamModelIds = ids;
  } catch { /* keep last good list */ }
}

async function fetchModelsDev() {
  try {
    const r = await httpGet("https://models.dev/api.json");
    const p = r.opencode;
    if (p && p.models) upstreamModelsDev = p.models;
  } catch { /* keep last good data */ }
}

function isFreeModelId(id) {
  return id && (id.endsWith("-free") || id.includes("-free-"));
}

function buildThinkingLevelMap(info) {
  const supported = new Set();
  if (info.reasoning_options) {
    for (const opt of info.reasoning_options) {
      if (opt.type === "toggle") { supported.add("off"); }
      if (opt.type === "effort" && opt.values) {
        for (const v of opt.values) supported.add(v);
      }
    }
  }
  if (supported.size === 0 && info.reasoning) {
    supported.add("low"); supported.add("medium"); supported.add("high");
  }
  if (supported.size === 0) return null;

  function findNearest(level) {
    const li = EFFORT_ORDER.indexOf(level);
    let best = null, bestDist = Infinity;
    for (const s of supported) {
      const si = EFFORT_ORDER.indexOf(s);
      if (si < 0) continue;
      const dist = Math.abs(si - li);
      if (dist < bestDist || (dist === bestDist && si > (EFFORT_ORDER.indexOf(best) ?? -1))) {
        best = s; bestDist = dist;
      }
    }
    return best;
  }

  const map = { off: null };
  for (const level of EFFORT_ORDER) {
    if (level === "off") continue;
    const mapped = findNearest(level);
    if (mapped) map[level] = mapped;
  }
  return map;
}

function buildModelRecord(id) {
  const info = upstreamModelsDev[id] || {};
  const ctx = info.limit?.context ?? 128_000;
  const out = info.limit?.output ?? 4_096;
  const thinkingLevelMap = buildThinkingLevelMap(info);
  const inputTypes = info.modalities?.input || ["text"];
  return { id, contextWindow: ctx, maxOutput: out, thinkingLevelMap, inputTypes };
}

// ─── Model list endpoint (GET /v1/models) ───────────────────────────

function serveModelList(req, res) {
  const agent = detectAgent(req.headers["user-agent"]);
  const data = upstreamModelIds.filter(isFreeModelId).map((id) => {
    const r = buildModelRecord(id);
    return {
      id,
      object: "model",
      created: Math.floor(Date.now() / 1000),
      owned_by: "opencode",
      context_window: r.contextWindow,
      max_output_tokens: r.maxOutput,
      thinking_level_map: r.thinkingLevelMap,
      supported_input: r.inputTypes,
    };
  });
  console.log(`📥 Models: ${agent} requested ${data.length} free models`);
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ object: "list", data }));
}

// ─── Logging ─────────────────────────────────────────────────────────

function logRequest(agent, method, url, parsedBody, allHeaders) {
  const ts = new Date().toISOString().slice(11, 19);
  const model = parsedBody?.model || "?";
  const msgCount = parsedBody?.messages?.length || 0;
  const hasTools = !!parsedBody?.tools;
  const toolCount = parsedBody?.tools?.length || 0;
  const reasoning = parsedBody?.reasoning_effort || parsedBody?.thinking?.type || "—";
  const stream = parsedBody?.stream ? "stream" : "sync";
  const tokens = parsedBody?.max_tokens || parsedBody?.max_completion_tokens || "—";

  console.log(`📥 ${ts} [${agent}] ${method} ${url} → model=${model} msgs=${msgCount} ${stream} tokens=${tokens} reasoning=${reasoning}${hasTools ? ` tools=${toolCount}` : ""}`);
  // Log agent-specific headers
  const interesting = ["user-agent","authorization","x-opencode-session","x-opencode-project","x-opencode-request","x-opencode-client","content-type","accept","x-api-key","x-reasonix-session","x-factory-api-key"];
  const hdrLog = {};
  for (const h of interesting) { if (allHeaders[h]) hdrLog[h] = allHeaders[h]; }
  console.log(`   headers: ${JSON.stringify(hdrLog)}`);
  // Log session-related body fields
  const sessionFields = {};
  for (const k of Object.keys(parsedBody || {})) {
    if (k.includes("session") || k.includes("thread") || k.includes("conversation") || k.includes("context") || k.includes("metadata")) {
      sessionFields[k] = typeof parsedBody[k] === "object" ? "[Object]" : parsedBody[k];
    }
  }
  if (Object.keys(sessionFields).length > 0) console.log(`   session: ${JSON.stringify(sessionFields)}`);
}

// ─── Body transformation (agent-aware) ──────────────────────────────

function transformBody(parsed, agent) {
  // Strip function-calling tools — upstream free models don't support them
  if (parsed.tools) {
    delete parsed.tools;
    delete parsed.tool_choice;
    delete parsed.parallel_tool_calls;
  }
  return parsed;
}

// Transform request headers per agent before forwarding to upstream
function transformHeaders(agent, headers) {
  // 1. Delete incoming host (proxy uses its own)
  delete headers.host;
  // 2. dirac sends Authorization: Bearer public — strip it, opencodeHeaders() injects the real one
  delete headers.authorization;
  // 3. Delete content-length (recalculated after body transform)
  delete headers["content-length"];
  // 4. Add opencode-compatible headers
  Object.assign(headers, opencodeHeaders());
  return headers;
}

// ─── Proxy to upstream ──────────────────────────────────────────────

function proxyToUpstream(req, res) {
  const agent = detectAgent(req.headers["user-agent"]);

  // Transform headers per agent (strip auth, inject opencode headers)
  const headers = { ...req.headers };
  transformHeaders(agent, headers);

  const isChat = req.url.includes("/chat/completions") || req.url.includes("/completions");

  const opts = {
    hostname: UPSTREAM_URL.hostname,
    port: UPSTREAM_URL.port || 443,
    path: "/zen" + req.url,
    method: req.method,
    headers,
    timeout: 300_000,
  };

  // Capture body for logging + transformation
  const MAX_BODY = 10 * 1024 * 1024; // 10MB limit
  let bodySize = 0;
  const chunks = [];
  req.on("data", (c) => {
    bodySize += c.length;
    if (bodySize > MAX_BODY) {
      req.destroy();
      if (!res.headersSent) {
        res.writeHead(413, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: { message: "Request body too large (max 10MB)", type: "proxy_error" } }));
      }
      return;
    }
    chunks.push(c);
  });
  req.on("end", () => {
    const rawBody = Buffer.concat(chunks).toString();
    let finalBody = rawBody;

    if (isChat && rawBody) {
      try {
        const parsed = JSON.parse(rawBody);
        logRequest(agent, req.method, req.url, parsed, req.headers);
        transformBody(parsed, agent);
        finalBody = JSON.stringify(parsed);
        // Recalculate Content-Length after body transformation
        delete headers["content-length"];
        headers["content-length"] = Buffer.byteLength(finalBody);
      } catch { /* pass through raw */ }
    }

    const proxyReq = https.request(opts, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res);
    });

    proxyReq.on("error", (e) => {
      if (!res.headersSent) {
        res.writeHead(502, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: { message: "Upstream error: " + e.message, type: "proxy_error" } }));
      }
    });

    proxyReq.write(finalBody);
    proxyReq.end();
  });
}

// ─── HTTP server ─────────────────────────────────────────────────────

function handleRequest(req, res) {
  // Health check
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ status: "ok", session: SESSION_ID, project: PROJECT_ID }));
  }

  // Model list
  if (req.url === "/v1/models" && req.method === "GET") {
    return serveModelList(req, res);
  }

  // Everything else → upstream
  proxyToUpstream(req, res);
}

// ─── Config writing ──────────────────────────────────────────────────

const HOME = os.homedir();

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function safeReadJson(filePath) {
  try { return parseJson(fs.readFileSync(filePath, "utf8"), null, true); }
  catch { return null; }
}

function safeReadToml(filePath) {
  try { return parseToml(fs.readFileSync(filePath, "utf8")); }
  catch { return null; }
}

// ── Droid ────────────────────────────────────────────────────────────

function setupDroid() {
  const cfgPath = path.join(HOME, ".factory", "settings.json");
  ensureDir(path.dirname(cfgPath));
  const existing = safeReadJson(cfgPath) || {};
  if (!existing.customModels) existing.customModels = [];

  // Remove our previously-injected entries (by marker)
  const models = existing.customModels.filter((m) => !m.__opencode_zen_proxy__);

  // Add free models
  for (const id of upstreamModelIds.filter(isFreeModelId)) {
    const info = upstreamModelsDev[id] || {};
    models.push({
      __opencode_zen_proxy__: true,
      model: id,
      displayName: id,
      baseUrl: `http://127.0.0.1:${CLI.port}/v1`,
      apiKey: "public",
      provider: "generic-chat-completion-api",
      maxOutputTokens: info.limit?.output ?? 4096,
      extraHeaders: {
        "User-Agent": "opencode/1.17.15/cli",
        "x-opencode-client": "cli",
        "x-opencode-session": SESSION_ID,
        "x-opencode-project": PROJECT_ID,
      },
    });
  }

  existing.customModels = models;
  fs.writeFileSync(cfgPath, stringifyJson(existing, null, 2) + "\n");
  console.log(`  ✅ Droid: ${cfgPath} (${models.length} models)`);
}

// ── Reasonix ─────────────────────────────────────────────────────────

function setupReasonix() {
  const cfgDir = path.join(HOME, ".reasonix");
  const cfgPath = path.join(cfgDir, "config.toml");
  ensureDir(cfgDir);
  const existing = safeReadToml(cfgPath) || {};

  // Ensure providers is an array
  if (!Array.isArray(existing.providers)) existing.providers = [];

  // Remove our previously-injected entries (by marker)
  existing.providers = existing.providers.filter((p) => !p._opencode_zen_proxy);

  // Add free models as separate [[providers]] entries (one model per provider)
  for (const id of upstreamModelIds.filter(isFreeModelId)) {
    const info = upstreamModelsDev[id] || {};
    existing.providers.push({
      _opencode_zen_proxy: true,
      name: id,
      kind: "openai",
      base_url: `http://127.0.0.1:${CLI.port}/v1`,
      api_key: "public",
      model: id,
      context_window: info.limit?.context ?? 128_000,
    });
  }

  fs.writeFileSync(cfgPath, stringifyToml(existing));
  console.log(`  ✅ Reasonix: ${cfgPath} (${existing.providers.length} providers)`);
}

// ── Dirac ────────────────────────────────────────────────────────────

function setupDirac() {
  const cfgDir = path.join(HOME, ".config", "dirac");
  ensureDir(cfgDir);
  const envPath = path.join(cfgDir, "proxy.env");
  const content = [
    `# opencode-zen proxy env — source this before running dirac`,
    `# Usage: source ${envPath} && dirac`,
    `export OPENAI_API_BASE="http://127.0.0.1:${CLI.port}/v1"`,
    `export OPENAI_API_KEY="public"`,
    `export OPENAI_BASE_URL="http://127.0.0.1:${CLI.port}/v1"`,
    `# Default model (override with: dirac -m <model>)`,
    `export DIRAC_MODEL="${upstreamModelIds.filter(isFreeModelId)[0] || ""}"`,
  ].join("\n") + "\n";

  fs.writeFileSync(envPath, content);
  console.log(`  ✅ Dirac: ${envPath}`);
  console.log(`     Usage: source ${envPath} && dirac -m <model>`);
}

// ─── Main ────────────────────────────────────────────────────────────

async function main() {
  // Always fetch upstream data (for both setup and runtime)
  {
    console.log("📡 Fetching upstream model list...");
    await Promise.all([fetchUpstreamModelIds(), fetchModelsDev()]);
    console.log(`   Found ${upstreamModelIds.length} upstream models, ${upstreamModelIds.filter(isFreeModelId).length} free`);

    if (CLI.setup) {
      console.log("\n📝 Writing agent configs...");
      if (CLI.agents.includes("droid")) setupDroid();
      if (CLI.agents.includes("reasonix")) setupReasonix();
      if (CLI.agents.includes("dirac")) setupDirac();
      console.log("\n✅ Done. Config files written.");
      return; // --setup only, don't start server
    }
  }

  // Start server
  const server = http.createServer(handleRequest);
  // Graceful shutdown
  const shutdown = () => {
    console.log("\n⏹️  Shutting down...");
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(1), 5000); // force exit after 5s
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  server.listen(CLI.port, "127.0.0.1", () => {
    console.log(`\n🚀 opencode-zen proxy listening on http://127.0.0.1:${CLI.port}`);
    console.log(`   Session: ${SESSION_ID}`);
    console.log(`   Project: ${PROJECT_ID}`);
    console.log(`   Upstream: ${UPSTREAM}`);
    console.log(`   Free models: ${upstreamModelIds.filter(isFreeModelId).join(", ")}`);
    console.log(`\n   Health:  curl http://127.0.0.1:${CLI.port}/health`);
    console.log(`   Models:  curl http://127.0.0.1:${CLI.port}/v1/models`);
    console.log(`   Chat:    curl -X POST http://127.0.0.1:${CLI.port}/v1/chat/completions \\
              -H "Content-Type: application/json" \\
              -d '{"model":"deepseek-v4-flash-free","messages":[{"role":"user","content":"Say PONG_OK"}]}'`);
  });

  // Periodic refresh
  setInterval(async () => {
    await Promise.all([fetchUpstreamModelIds(), fetchModelsDev()]);
  }, MODEL_LIST_CACHE);
}

main().catch((e) => { console.error("Fatal:", e.message); process.exit(1); });
