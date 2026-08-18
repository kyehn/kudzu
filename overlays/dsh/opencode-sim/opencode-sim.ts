// OpenCode CLI 客户端模拟 — TypeScript 源码。
//
// 运行方式：nix 构建期经 esbuild 编译为纯 ESM 注入 pi-ai 的
// openai-completions api（Node 24 默认 type stripping 禁止 node_modules 内
// .ts：ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING，故不能直接注入源码）；
// dsh 启动参数 --expose-internals 已由 overlays/dsh/default.nix 注入。
//
// 本文件为传输层/请求装配层（undici Agent + fetch 替换 + 响应解压）；
// wire 特征（headers/动态 id/body 规范化）在独立纯逻辑模块
// opencode-wire.ts（零外部依赖，node --test 直接测）。基准同为
// overlays/reasonix/opencode/（只读，不得修改）——_tls-fingerprint.json 与
// POST_zen_v1_*.json 为 opencode CLI v1.18.18（Bun/BoringSSL）真实抓包。
import { Readable } from "node:stream";
import zlib from "node:zlib";
import { Agent, request } from "undici";
import {
  normalizeHeaders,
  opencodeBodyRewrite,
  opencodeSimHeaders,
} from "./opencode-wire.ts";

// -- 传输层（undici Agent）。TLS 参数对齐 _tls-fingerprint.json 的 ClientHello：
//   cipher 套件顺序、TLS1.2–1.3 版本、X25519/P-256/P-384 曲线顺序、
//   ALPN 只有 http/1.1、sigalgs（经 openssl.cnf——OpenSSL 3.x 过滤
//   rsa_pkcs1_sha1，实际 8 项与基准前 8 项一致，见 openssl.cnf 注释）。
//   如实记录的差异（Node/OpenSSL 栈，非 BoringSSL）：ClientHello 扩展的
//   线序（encrypt_then_mac 多、status_request/SCT 缺）由 OpenSSL 硬编码
//   不可控；断言测试 opencode-tls.test.mjs 逐项断言可配置维度并如实报告。
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

let opencodeAgent: Agent | undefined;

/** overrides 仅用于测试/特殊网关（如 rejectUnauthorized、servername）。 */
export function buildOpencodeAgent(overrides: Record<string, unknown> = {}) {
  return new Agent({
    connect: {
      // 抓包基准 alpn=["http/1.1"]（opencode CLI 走 HTTP/1.1）
      allowH2: false,
      // undici 的 connect 选项直接透传给 node:tls.connect，故 TLS 选项在顶层
      minVersion: "TLSv1.2",
      maxVersion: "TLSv1.3",
      ciphers: TLS_CIPHERS,
      // 基准 groups=[29,23,24] = X25519, prime256v1, secp384r1（0x0018；
      // 旧注释误作 x25519-mlkem768，已实测修正）；Node 逐项支持，顺序保持
      ecdhCurve: "X25519:prime256v1:secp384r1",
      honorCipherOrder: true,
      ...overrides,
    },
  });
}

// -- 响应解压：undici request() 不解压（实测：gzip/deflate/br 魔数原样保留），
//   需按 Content-Encoding 显式解码。与 reasonix decompressBody 同语义；
//   基准抓包响应无 Content-Encoding（SSE identity）。zstd：Node 无内置
//   解压器（reasonix 用 klauspost/compress/zstd），如实抛错而非静默损坏。
function decodeBody(
  buffer: Uint8Array,
  contentEncoding: string | undefined,
): Uint8Array {
  switch (contentEncoding?.trim().toLowerCase()) {
    case undefined:
    case "":
    case "identity":
      return buffer;
    case "gzip":
      return zlib.gunzipSync(buffer);
    case "deflate": {
      try {
        return zlib.inflateSync(buffer);
      } catch {
        // 部分服务器发 raw DEFLATE（RFC 1951）而非 zlib 封装（RFC 1950）
        return zlib.inflateRawSync(buffer);
      }
    }
    case "br":
      return zlib.brotliDecompressSync(buffer);
    case "zstd":
      throw new Error(
        "unsupported Content-Encoding 'zstd': Node 无内置 zstd 解压器 " +
          "（reasonix 用 klauspost/compress/zstd）；基准抓包响应无压缩，" +
          "该路径如实报错而非静默损坏。",
      );
    default:
      throw new Error(`unsupported Content-Encoding '${contentEncoding}'`);
  }
}

// -- undici request() 响应 → SDK 期望的 Response 兼容对象 --
interface OpenCodeResponseLike {
  ok: boolean;
  status: number;
  statusText: string;
  headers: Headers;
  body: ReadableStream<Uint8Array>;
  json(): Promise<unknown>;
  text(): Promise<string>;
  arrayBuffer(): Promise<Uint8Array>;
}

function opencodeResponse(resp: {
  statusCode: number;
  headers: string[] | Record<string, string | string[] | undefined>;
  body: AsyncIterable<Uint8Array>;
}): Promise<OpenCodeResponseLike> {
  const status = resp.statusCode;
  const headers = new Headers();
  if (Array.isArray(resp.headers)) {
    for (let i = 0; i + 1 < resp.headers.length; i += 2) {
      headers.append(resp.headers[i], resp.headers[i + 1]);
    }
  } else {
    for (const [key, value] of Object.entries(resp.headers ?? {})) {
      if (value === undefined) continue;
      if (Array.isArray(value)) {
        for (const v of value) headers.append(key, v);
      } else {
        headers.append(key, value);
      }
    }
  }

  // 惰性缓存：undici 响应流只消费一次，body 流 / json() / text() /
  // arrayBuffer() 全部复用同一份解码结果（重复消费同一流会得到空字节）。
  let decodedPromise: Promise<Uint8Array> | undefined;
  const readAll = (): Promise<Uint8Array> => {
    decodedPromise ??= (async () => {
      const chunks: Uint8Array[] = [];
      let total = 0;
      for await (const chunk of resp.body) {
        chunks.push(chunk);
        total += chunk.byteLength;
      }
      const merged = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.byteLength;
      }
      return decodeBody(merged, headers.get("content-encoding") ?? undefined);
    })();
    return decodedPromise;
  };

  // 基准响应无 Content-Encoding（SSE identity）：body 流式透传，SDK 边收边
  // 解析；非 identity 时缓冲整段解压后以单块流吐出（正确性优先）。
  const encoding = headers.get("content-encoding")?.trim().toLowerCase();
  const isIdentity = !encoding || encoding === "" || encoding === "identity";
  const body: ReadableStream<Uint8Array> = isIdentity
    ? (Readable.toWeb(resp.body) as ReadableStream<Uint8Array>)
    : new ReadableStream({
        async pull(controller) {
          controller.enqueue(await readAll());
          controller.close();
        },
      });

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

/**
 * 返回 SDK fetch 替换：trigger 请求（x-opencode 头存在）装配完整 opencode
 * wire 特征（headers + body 规范化）；非 trigger 请求原样转发。
 *
 * 用 undici 低层 request() 而非 fetch()：undici fetch 会按 fetch 规范附加
 * accept-language: * 与 sec-fetch-mode: cors（基准 wire 无此二头，见
 * POST_zen_v1_chat_completions.json），且该附加发生在 dispatcher 层，无法
 * 用 headers 对象清除；request() 无此语义，再包一层最小 Response 兼容面
 * 供 OpenAI SDK 消费（json/text/body/headers）。
 */
export function opencodeFactoryFetch({
  tls = {},
}: {
  tls?: Record<string, unknown>;
} = {}) {
  if (!opencodeAgent) {
    opencodeAgent = buildOpencodeAgent(tls);
  }
  return (url: string | URL, init: RequestInit = {}) => {
    const raw = normalizeHeaders(init.headers);
    const trigger =
      raw["x-opencode-client"] !== undefined ||
      raw["x-opencode-project"] !== undefined;
    const headers = trigger ? opencodeSimHeaders(raw) : raw;
    const body =
      trigger && typeof init.body === "string"
        ? opencodeBodyRewrite(init.body)
        : init.body;
    return request(url, {
      ...init,
      headers,
      body,
      // undici request() 默认 decompress:true——带 Accept-Encoding 声明时自动
      // 解压响应却保留 Content-Encoding 头，再经 decodeBody 会双重解压
      //（实测 Z_BUF_ERROR）。统一由 opencodeResponse/decodeBody 显式处理。
      decompress: false,
      dispatcher: opencodeAgent as unknown as Dispatcher,
    }).then(opencodeResponse);
  };
}
