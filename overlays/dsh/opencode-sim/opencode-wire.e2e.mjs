// 端到端 wire 校验：直接在 dsh store 注入产物 opencode-sim.mjs 上发请求，
// 本地 echo server 捕获 undici 实际 wire headers/body，与 protected 基准
// overlays/reasonix/opencode/POST_zen_v1_chat_completions.json 比对。

import { readFileSync } from "node:fs";
import http from "node:http";

const STORE =
  process.env.DSH_STORE ??
  "/nix/store/vzbilns003ig0r4jpshl2m97pdjq05j1-dsh-0.1.0-rc.7";
const { opencodeFactoryFetch } = await import(
  `file://${STORE}/lib/node_modules/@deepseek-ai/dsh/opencode-sim/opencode-sim.mjs`
);

// 捕获原始行序（undici 序列化后的真实 wire 顺序）
let captured = [];
const server = http.createServer((req, res) => {
  captured = [];
  captured.push(`${req.method} ${req.url} HTTP/${req.httpVersion}`);
  for (const [k, v] of Object.entries(req.headers)) captured.push(`${k}: ${v}`);
  let raw = "";
  req.on("data", (c) => (raw += c));
  req.on("end", () => {
    captured.push(`\n${raw}`);
    res.writeHead(200, { "Content-Type": "text/event-stream" });
    res.end('data: {"ok":true}\n\n');
  });
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;

// 基准（只读 protected）
const base = JSON.parse(
  readFileSync(
    new URL(
      "../../reasonix/opencode/POST_zen_v1_chat_completions.json",
      import.meta.url,
    ).pathname,
    "utf-8",
  ),
);
const baseHeaders = base.request.headers;
const baseBody = JSON.parse(base.request.body);
const order = Object.keys(baseBody);

// 输入体：故意携带需要被重写的字段
const inputBody = {
  model: "mimo-v2.5-free",
  messages: [
    { role: "system", content: "You are opencode, an interactive CLI tool." },
  ],
  max_completion_tokens: 32000,
  reasoning_effort: "medium",
  temperature: 0.5,
  tools: [{ type: "function", function: { name: "bash", parameters: {} } }],
  stream: true,
  stream_options: { include_usage: true },
  prompt_cache_key: "x",
  store: true,
};

const host = `127.0.0.1:${port}`;
const fetch = opencodeFactoryFetch();
const res = await fetch(`http://${host}/zen/v1/chat/completions`, {
  method: "POST",
  headers: {
    Authorization: "Bearer public",
    "Content-Type": "application/json",
    "x-opencode-client": "cli",
    "x-opencode-project": "global",
  },
  body: JSON.stringify(inputBody),
});
console.log("resp status:", res.status);

// 解析捕获
const raw = captured.join("\n");
const [head, ...bodyLines] = raw.split("\n\n");
const wireHeaders = {};
for (const line of head.split("\n").slice(1)) {
  const i = line.indexOf(":");
  wireHeaders[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim();
}
const wireBody = JSON.parse(bodyLines.join("\n\n"));

const fail = [];
// UA 权威值
if (wireHeaders["user-agent"] !== baseHeaders["User-Agent"])
  fail.push(
    `UA: got=${wireHeaders["user-agent"]} want=${baseHeaders["User-Agent"]}`,
  );
if (wireHeaders["accept"] !== baseHeaders["Accept"])
  fail.push(`Accept: ${wireHeaders["accept"]}`);
if (wireHeaders["accept-encoding"] !== baseHeaders["Accept-Encoding"])
  fail.push(`Accept-Encoding: ${wireHeaders["accept-encoding"]}`);
for (const h of [
  "authorization",
  "content-type",
  "x-opencode-client",
  "x-opencode-project",
]) {
  if (!wireHeaders[h]) fail.push(`missing header: ${h}`);
}
for (const h of ["x-opencode-request", "x-opencode-session"]) {
  if (!/^(msg_|ses_)/.test(wireHeaders[h] ?? ""))
    fail.push(`bad dynamic id: ${h}=${wireHeaders[h]}`);
}
// 动态 id 形似基准
if (!/^msg_[0-9a-zA-Z]{26}$/.test(wireHeaders["x-opencode-request"]))
  fail.push("msg id shape mismatch");
if (!/^ses_[0-9a-zA-Z]{26}$/.test(wireHeaders["x-opencode-session"]))
  fail.push("ses id shape mismatch");
// body 键序 = 基准键序
const gotOrder = Object.keys(wireBody);
if (gotOrder.join() !== order.join())
  fail.push(`body order: got=${gotOrder} want=${order}`);
// 重写语义
if (wireBody.max_tokens !== 32000)
  fail.push(`max_tokens: ${wireBody.max_tokens}`);
if ("max_completion_tokens" in wireBody)
  fail.push("max_completion_tokens 未删除");
if ("reasoning_effort" in wireBody) fail.push("reasoning_effort 未删除");
if ("temperature" in wireBody) fail.push("temperature 未删除");
if ("prompt_cache_key" in wireBody || "store" in wireBody)
  fail.push("cache/store 未删除");
if (wireBody.tool_choice !== "auto")
  fail.push(`tool_choice: ${wireBody.tool_choice}`);
if (wireBody.stream !== true || !wireBody.stream_options)
  fail.push("stream 参数丢失");
if (!wireBody.tools?.length) fail.push("tools 丢失");

console.log("--- wire 顺序 ---");
console.log(head.split("\n").join("\n"));
console.log("--- 结果 ---");
console.log(
  fail.length ? `FAIL\n${fail.join("\n")}` : "PASS: headers/body 全对齐",
);
server.close();
process.exit(fail.length ? 1 : 0);
