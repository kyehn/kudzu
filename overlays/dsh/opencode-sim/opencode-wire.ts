// OpenCode wire 特征 — 纯逻辑层（headers / 动态 id / body 规范化）。
// 零外部依赖（仅 node:crypto），可被 node --test 直接测试（type stripping）。
// 基准：overlays/reasonix/opencode/（只读）——opencode CLI v1.18.18 真实抓包；
// 实现语义与 reasonix internal/provider/openai/opencode.go 及 opencode_id.go
// （id.ts create() 移植）保持一致。
import { randomBytes } from "node:crypto";

// -- 常量（与 alignment.patch 的 opencodeUserAgent / opencodeAcceptEncoding
//    逐字节一致，勿单独改动）--
export const OPENCODE_USER_AGENT =
  "opencode/1.18.18 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14";
export const OPENCODE_ACCEPT = "*/*";
export const OPENCODE_ACCEPT_ENCODING = "gzip, deflate, br, zstd";

// -- 会话/请求 ID：opencode src/id/id.ts create() 的逐字节移植 --
const ID_LENGTH = 26;
const ID_BASE62 =
  "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

let lastIdTimestamp = 0;
let idCounter = 0;

function randomBase62(length: number): string {
  let result = "";
  const bytes = randomBytes(length);
  for (let i = 0; i < length; i++) {
    result += ID_BASE62[bytes[i] % 62];
  }
  return result;
}

/**
 * 移植 id.ts create()：毫秒单调计数器编码为 6 字节大端 + 26 字符 base62。
 * @param prefix - "ses" | "msg"
 * @param direction - "descending"（会话，时间取反）| "ascending"（请求）
 * @param timestamp - 测试用固定时间戳
 */
export function opencodeCreate(
  prefix: "ses" | "msg",
  direction: "ascending" | "descending",
  timestamp?: number,
): string {
  const currentTimestamp = timestamp ?? Date.now();

  if (currentTimestamp !== lastIdTimestamp) {
    lastIdTimestamp = currentTimestamp;
    idCounter = 0;
  }
  idCounter++;

  let now = BigInt(currentTimestamp) * BigInt(0x1000) + BigInt(idCounter);
  now = direction === "descending" ? ~now : now;

  const timeBytes = Buffer.alloc(6);
  for (let i = 0; i < 6; i++) {
    timeBytes[i] = Number((now >> BigInt(40 - 8 * i)) & BigInt(0xff));
  }
  return `${prefix}_${timeBytes.toString("hex")}${randomBase62(ID_LENGTH - 12)}`;
}

// x-opencode-session 每客户端实例固定（每次模块加载一个），与 opencode CLI 相同
export const opencodeSessionId = opencodeCreate("ses", "descending");

// -- headers：与 reasonix opencode.go applyOpenCodeHeaders 同语义 ——
//    删除 canonical 冲突后写小写 x-opencode-*；UA/Accept/Accept-Encoding 权威值。
//    另清理 undici/OpenAI SDK 附加而 opencode CLI wire 不存在的头：
//    accept-language / sec-fetch-mode（undici fetch 默认）与 x-stainless-*（SDK）。
const DELETE_HEADERS = new Set([
  "user-agent",
  "accept",
  "accept-encoding",
  "accept-language",
  "sec-fetch-mode",
  "x-opencode-client",
  "x-opencode-session",
  "x-opencode-request",
  "x-opencode-project",
]);

export type HeadersRecord = Record<string, string>;

/** 把 Headers 实例或 record 统一成小写键 record（SDK 动态头也在此可见）。 */
export function normalizeHeaders(
  headers: Headers | HeadersRecord | undefined | null,
): HeadersRecord {
  const out: HeadersRecord = {};
  if (!headers) return out;
  if (typeof headers.get === "function") {
    for (const [key, value] of (headers as Headers).entries()) out[key] = value;
  } else {
    Object.assign(out, headers);
  }
  return out;
}

/**
 * 按 opencode CLI wire 重写请求头。仅在 trigger 头（x-opencode-client /
 * x-opencode-project）存在时调用，非 trigger 请求保持原样。
 */
export function opencodeSimHeaders(headers: HeadersRecord): HeadersRecord {
  const out: HeadersRecord = {};
  for (const [key, value] of Object.entries(headers)) {
    const lower = key.toLowerCase();
    if (DELETE_HEADERS.has(lower) || lower.startsWith("x-stainless-")) {
      continue;
    }
    out[key] = value;
  }
  out["User-Agent"] = OPENCODE_USER_AGENT;
  out.Accept = OPENCODE_ACCEPT;
  out["Accept-Encoding"] = OPENCODE_ACCEPT_ENCODING;
  out["x-opencode-client"] = "cli";
  out["x-opencode-project"] = "global";
  out["x-opencode-request"] = opencodeCreate("msg", "ascending");
  out["x-opencode-session"] = opencodeSessionId;
  return out;
}

// -- body 规范化：对齐 reasonix opencode.go marshalOpenCodeRequest ——
//    键序 model → max_tokens → messages → tools → tool_choice → stream →
//    stream_options；删除 temperature/reasoning_effort/thinking/
//    prompt_cache_key/store（SDK 键不复制到 out 即被丢弃）；
//    max_completion_tokens → max_tokens；tools 存在时 tool_choice="auto"；
//    assistant tool_calls 消息必须携带 reasoning_content 键（丢失时补空串，
//    否则后端 400）。

/** 返回重写后的 JSON 字符串；输入非 JSON 对象时原样返回（不吞错误）。 */
export function opencodeBodyRewrite(rawBody: string): string {
  let body: unknown;
  try {
    body = JSON.parse(rawBody);
  } catch {
    return rawBody;
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return rawBody;
  }
  const src = body as Record<string, unknown>;
  const out: Record<string, unknown> = {};

  out.model = src.model;
  const maxTokens = src.max_tokens ?? src.max_completion_tokens;
  if (maxTokens != null) out.max_tokens = maxTokens;
  out.messages = src.messages;

  const tools = src.tools;
  if (Array.isArray(tools) && tools.length > 0) {
    out.tools = tools;
    // opencode CLI：只要 tools 存在就发 tool_choice: "auto"（无论 SDK 怎么设）
    out.tool_choice = "auto";
  }
  if (src.stream != null) out.stream = src.stream;
  if (src.stream_options != null) out.stream_options = src.stream_options;

  // assistant tool_calls 回合必须带 reasoning_content（reasonix 同款语义）
  if (Array.isArray(out.messages)) {
    for (const message of out.messages as Record<string, unknown>[]) {
      if (
        message?.role === "assistant" &&
        Array.isArray(message.tool_calls) &&
        message.tool_calls.length > 0 &&
        !("reasoning_content" in message)
      ) {
        message.reasoning_content = "";
      }
    }
  }

  // 其余 SDK 键不落盘，与 reasonix openCodeRequest 仅 7 键一致
  return JSON.stringify(out);
}
