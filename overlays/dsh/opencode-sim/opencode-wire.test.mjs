// OpenCode wire 特征单测（opencode-wire.ts 纯逻辑层）。
// 运行：node --experimental-strip-types --test opencode-wire.test.mjs
//（node 24 可省略 flag；flag 保证 node 22.6+ 亦可运行）。

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  OPENCODE_ACCEPT,
  OPENCODE_ACCEPT_ENCODING,
  OPENCODE_USER_AGENT,
  opencodeBodyRewrite,
  opencodeCreate,
  opencodeSessionId,
  opencodeSimHeaders,
} from "./opencode-wire.ts";

// -- id --
test("opencodeCreate 格式：prefix + 6 字节 hex + 14 位 base62", () => {
  const id = opencodeCreate("msg", "ascending", 1750000000000);
  assert.match(id, /^msg_[0-9a-f]{12}[0-9A-Za-z]{14}$/);
  assert.equal(id.length, 4 + 26);
});

test("opencodeCreate 同时间戳计数单调递增（ascending）", () => {
  const ts = 1750000000000;
  const a = opencodeCreate("msg", "ascending", ts);
  const b = opencodeCreate("msg", "ascending", ts);
  assert.notEqual(a, b);
  // 计数编码进时间字节（now = ts*4096 + counter），同一毫秒第二次调用
  // 的时间部分应递增 1；后缀 base62 随机部分长度一致
  assert.equal(
    BigInt(`0x${b.slice(4, 16)}`) - BigInt(`0x${a.slice(4, 16)}`),
    1n,
  );
  assert.equal(a.slice(16).length, 14);
});

test("opencodeCreate descending 与 ascending 时间字节不同", () => {
  const ts = 1750000000000;
  const up = opencodeCreate("msg", "ascending", ts);
  const down = opencodeCreate("ses", "descending", ts);
  assert.notEqual(up.slice(4, 16), down.slice(4, 16));
});

test("opencodeSessionId 为 ses_ 前缀且单次加载固定", () => {
  assert.match(opencodeSessionId, /^ses_/);
  assert.equal(opencodeSessionId.length, 4 + 26);
});

// -- headers --
test("opencodeSimHeaders 写入全部权威 wire 头", () => {
  const h = opencodeSimHeaders({ "x-opencode-client": "cli" });
  assert.equal(h["User-Agent"], OPENCODE_USER_AGENT);
  assert.equal(h.Accept, OPENCODE_ACCEPT);
  assert.equal(h["Accept-Encoding"], OPENCODE_ACCEPT_ENCODING);
  assert.equal(h["x-opencode-client"], "cli");
  assert.equal(h["x-opencode-project"], "global");
  assert.match(h["x-opencode-request"], /^msg_/);
  assert.equal(h["x-opencode-session"], opencodeSessionId);
});

test("opencodeSimHeaders 清理 SDK/undici 附加头", () => {
  const h = opencodeSimHeaders({
    "User-Agent": "node",
    Accept: "application/json",
    "Accept-Encoding": "identity",
    "accept-language": "en",
    "sec-fetch-mode": "cors",
    "x-stainless-package-version": "1.2.3",
    "x-opencode-client": "cli",
    "X-Opencode-Session": "evil",
    "X-Opencode-Request": "evil",
    "X-Opencode-Project": "evil",
    "x-opencode-request-extra": "keep",
  });
  // 权威值替换（非删除）：UA/Accept/Accept-Encoding 与 x-opencode-* 重写
  assert.equal(h["User-Agent"], OPENCODE_USER_AGENT);
  assert.equal(h.Accept, OPENCODE_ACCEPT);
  assert.equal(h["Accept-Encoding"], OPENCODE_ACCEPT_ENCODING);
  assert.equal(h["x-opencode-client"], "cli");
  assert.equal(h["x-opencode-project"], "global");
  assert.equal(h["x-opencode-session"], opencodeSessionId);
  assert.equal(h["x-opencode-request-extra"], "keep");
  // 纯删除：undici fetch 附加头、SDK x-stainless-*、传入的冲突 x-opencode-*
  for (const gone of [
    "accept-language",
    "sec-fetch-mode",
    "x-stainless-package-version",
  ]) {
    assert.ok(!(gone in h), `${gone} 应被清理`);
  }
});

// -- body 规范化 --
test("opencodeBodyRewrite 键序 = model,max_tokens,messages,tools,tool_choice,stream,stream_options", () => {
  const out = opencodeBodyRewrite(
    JSON.stringify({
      model: "m",
      max_tokens: 64,
      messages: [{ role: "user", content: "hi" }],
      tools: [{ type: "function" }],
      stream: true,
      stream_options: { include_usage: true },
    }),
  );
  assert.deepEqual(Object.keys(JSON.parse(out)), [
    "model",
    "max_tokens",
    "messages",
    "tools",
    "tool_choice",
    "stream",
    "stream_options",
  ]);
  assert.equal(JSON.parse(out).tool_choice, "auto");
});

test("opencodeBodyRewrite 删除 temperature/reasoning_effort/prompt_cache_key/store", () => {
  const out = JSON.parse(
    opencodeBodyRewrite(
      JSON.stringify({
        model: "m",
        temperature: 0.7,
        reasoning_effort: "high",
        prompt_cache_key: "cache",
        store: true,
        messages: [{ role: "user", content: "hi" }],
      }),
    ),
  );
  for (const gone of [
    "temperature",
    "reasoning_effort",
    "prompt_cache_key",
    "store",
  ]) {
    assert.ok(!(gone in out), `${gone} 应被删除`);
  }
});

test("opencodeBodyRewrite max_completion_tokens 映射为 max_tokens", () => {
  const parsed = JSON.parse(
    opencodeBodyRewrite(
      JSON.stringify({ model: "m", max_completion_tokens: 100, messages: [] }),
    ),
  );
  assert.equal(parsed.max_tokens, 100);
  assert.ok(!("max_completion_tokens" in parsed));
});

test("opencodeBodyRewrite 无 tools 时不发 tool_choice", () => {
  const parsed = JSON.parse(
    opencodeBodyRewrite(
      JSON.stringify({
        model: "m",
        messages: [{ role: "user", content: "hi" }],
      }),
    ),
  );
  assert.ok(!("tools" in parsed));
  assert.ok(!("tool_choice" in parsed));
});

test("reasoning_content：已有保留、丢失补空串、user 消息不动", () => {
  const kept = JSON.parse(
    opencodeBodyRewrite(
      JSON.stringify({
        model: "m",
        messages: [
          {
            role: "assistant",
            tool_calls: [{ id: "c1" }],
            reasoning_content: "COT",
          },
        ],
      }),
    ),
  );
  assert.equal(kept.messages[0].reasoning_content, "COT");

  const padded = JSON.parse(
    opencodeBodyRewrite(
      JSON.stringify({
        model: "m",
        messages: [{ role: "assistant", tool_calls: [{ id: "c1" }] }],
      }),
    ),
  );
  assert.equal(padded.messages[0].reasoning_content, "");

  const user = JSON.parse(
    opencodeBodyRewrite(
      JSON.stringify({
        model: "m",
        messages: [{ role: "user", content: "x" }],
      }),
    ),
  );
  assert.ok(!("reasoning_content" in user.messages[0]));
});

test("opencodeBodyRewrite 非法 JSON 原样返回", () => {
  assert.equal(opencodeBodyRewrite("not-json"), "not-json");
});
