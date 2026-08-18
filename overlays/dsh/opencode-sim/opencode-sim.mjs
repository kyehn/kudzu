// OpenCode CLI 客户端模拟 — 与 overlays/reasonix/alignment.patch 同源基准。
// 特征基准: overlays/reasonix/opencode/（_tls-fingerprint.json 与 POST_zen_v1_*.json
// 为 opencode CLI v1.18.18（Bun/BoringSSL）的真实抓包；可用
// .github/reasonix-config/tests/test_consistency.py 拦截版本漂移）。
// 实现语义与 reasonix 侧 internal/provider/openai/opencode.go（headers + 解压）与
// opencode_id.go（id.ts create() 移植）保持一致。

// -- 常量（与 alignment.patch 的 opencodeUserAgent / opencodeAcceptEncoding
//    逐字节一致，勿单独改动）--
export const OPENCODE_USER_AGENT =
  "opencode/1.18.18 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14";
export const OPENCODE_ACCEPT = "*/*";
export const OPENCODE_ACCEPT_ENCODING = "gzip, deflate, br, zstd";

// -- 会话/请求 ID：opencode src/id/id.ts create() 的逐字节移植 --
import { randomBytes } from "node:crypto";

const ID_LENGTH = 26;
const ID_BASE62 =
  "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

let lastIdTimestamp = 0;
let idCounter = 0;

function randomBase62(length) {
  let result = "";
  const bytes = randomBytes(length);
  for (let i = 0; i < length; i++) {
    result += ID_BASE62[bytes[i] % 62];
  }
  return result;
}

export function opencodeCreate(prefix, direction, timestamp) {
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
  return (
    prefix + "_" + timeBytes.toString("hex") + randomBase62(ID_LENGTH - 12)
  );
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
export function opencodeSimHeaders(headers) {
  headers = { ...headers };
  for (const key of Object.keys(headers)) {
    const lower = key.toLowerCase();
    if (DELETE_HEADERS.has(lower) || lower.startsWith("x-stainless-"))
      delete headers[key];
  }
  headers["User-Agent"] = OPENCODE_USER_AGENT;
  headers["Accept"] = OPENCODE_ACCEPT;
  headers["Accept-Encoding"] = OPENCODE_ACCEPT_ENCODING;
  headers["x-opencode-client"] = "cli";
  headers["x-opencode-project"] = "global";
  headers["x-opencode-request"] = opencodeCreate("msg", "ascending");
  headers["x-opencode-session"] = opencodeSessionId;
  return headers;
}

import { Readable } from "node:stream";
// -- 传输层（undici Agent）。TLS 参数对齐 _tls-fingerprint.json 的 ClientHello：
//   cipher 套件顺序、TLS1.2–1.3 版本、X25519 曲线优先、ALPN 只有 http/1.1。
//   已知限制（Node/OpenSSL 栈，非 BoringSSL）：ClientHello 的扩展排列顺序与
//   signature algorithms 顺序无法由 Node 控制，故 JA3/JA4 与基准存在扩展段差异；
//   cipher 段与版本段一致。若要逐字节一致需 Bun 运行时或 utls 代理层。
import { Agent, request } from "undici";

const TLS_CIPHERS = [
  // TLS 1.3（0x1301 0x1302 0x1303）
  "TLS_AES_128_GCM_SHA256",
  "TLS_AES_256_GCM_SHA384",
  "TLS_CHACHA20_POLY1305_SHA256",
  // TLS 1.2：0xC02B 0xC02F 0xC02C 0xC030（ECDHE GCM）
  "ECDHE-ECDSA-AES128-GCM-SHA256",
  "ECDHE-RSA-AES128-GCM-SHA256",
  "ECDHE-ECDSA-AES256-GCM-SHA384",
  "ECDHE-RSA-AES256-GCM-SHA384",
  // 0xCCA9 0xCCA8（CHACHA20）
  "ECDHE-ECDSA-CHACHA20-POLY1305",
  "ECDHE-RSA-CHACHA20-POLY1305",
  // 0xC009 0xC013 0xC00A 0xC014（ECDHE SHA1）
  "ECDHE-ECDSA-AES128-SHA",
  "ECDHE-RSA-AES128-SHA",
  "ECDHE-ECDSA-AES256-SHA",
  "ECDHE-RSA-AES256-SHA",
  // 0x009C 0x009D 0x002F 0x0035（RSA）
  "AES128-GCM-SHA256",
  "AES256-GCM-SHA384",
  "AES128-SHA",
  "AES256-SHA",
].join(":");

let opencodeAgent;

// overrides 仅用于测试/特殊网关（如 rejectUnauthorized、servername）
export function buildOpencodeAgent(overrides = {}) {
  return new Agent({
    connect: {
      // 抓包基准 alpn=["http/1.1"]（opencode CLI 走 HTTP/1.1）
      allowH2: false,
      // undici 的 connect 选项直接透传给 node:tls.connect，故 TLS 选项在顶层
      minVersion: "TLSv1.2",
      maxVersion: "TLSv1.3",
      ciphers: TLS_CIPHERS,
      // 基准 groups=[29,23,24]（X25519, prime256v1, x25519-mlkem768）；
      // Node 不支持 mlkem768，取前两组并保持顺序
      ecdhCurve: "X25519:prime256v1",
      honorCipherOrder: true,
      ...overrides,
    },
  });
}

export function opencodeFactoryFetch({ tls } = {}) {
  if (!opencodeAgent) {
    opencodeAgent = buildOpencodeAgent(tls);
  }
  // 用 undici 低层 request() 而非 fetch()：undici fetch 会按 fetch 规范附加
  // accept-language: * 与 sec-fetch-mode: cors（基准 wire 无此二头，见
  // overlays/reasonix/opencode/POST_zen_v1_chat_completions.json），且该附加
  // 发生在 dispatcher 层，无法用 headers 对象清除；request() 无此语义，
  // 再包一层最小 Response 兼容面供 OpenAI SDK 消费（json/text/body/headers）。
  // OpenAI SDK 还会在每次请求动态附加 x-stainless-*（createClient 层删除
  // 无效），故在请求发出前按 trigger 条件做最终清理（同注入点语义）。
  return (url, init) => {
    const raw = normalizeHeaders(init.headers);
    const headers =
      raw["x-opencode-client"] || raw["x-opencode-project"]
        ? opencodeSimHeaders(raw)
        : raw;
    return request(url, { ...init, headers, dispatcher: opencodeAgent }).then(
      opencodeResponse,
    );
  };
}

/** 把 Headers 实例或 record 统一成小写键 record（SDK 动态头也在此可见）。 */
function normalizeHeaders(headers) {
  const out = {};
  if (!headers) return out;
  if (typeof headers.get === "function") {
    for (const [key, value] of headers.entries()) out[key] = value;
  } else {
    Object.assign(out, headers);
  }
  return out;
}

// -- undici request() 响应 → SDK 期望的 Response 兼容对象 --
function opencodeResponse(resp) {
  const status = resp.statusCode;
  const headers = new Headers();
  if (Array.isArray(resp.headers)) {
    for (let i = 0; i + 1 < resp.headers.length; i += 2) {
      headers.append(resp.headers[i], resp.headers[i + 1]);
    }
  } else {
    for (const [key, value] of Object.entries(resp.headers ?? {})) {
      headers.append(key, value);
    }
  }
  const body = Readable.toWeb(resp.body);
  const readAll = async () => {
    const reader = body.getReader();
    const chunks = [];
    let total = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      total += value.byteLength;
    }
    const merged = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      merged.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return merged;
  };
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    headers,
    body,
    json: async () => JSON.parse(new TextDecoder().decode(await readAll())),
    text: async () => new TextDecoder().decode(await readAll()),
    arrayBuffer: async () => readAll(),
  };
}
