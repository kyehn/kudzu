/**
 * dsh HTTP-layer patch: reproduce the opencode CLI wire fingerprint.
 *
 * Loaded via `node --import` before dsh boots. It wraps the global fetch:
 * requests whose URL is an opencode Zen endpoint get the real CLI's
 * JA3 ClientHello (via node-tls-client), User-Agent, Accept-Encoding and
 * lowercase x-opencode-* headers (request ID generated per request, session
 * ID fixed per process — exactly like the CLI). Every other request is
 * passed through untouched, so this patch does not participate in unrelated
 * traffic.
 *
 * The UA and header generation logic mirrors the real client
 * (packages/opencode/src/session/llm/request.ts) and the proven port in
 * `overlays/reasonix/alignment.patch` (opencode/1.18.18).
 */

import { initTLS, Session } from "node-tls-client";

/** opencode Zen base URL (host + path prefix). */
const ZEN_BASE = "opencode.ai/zen/";

const opencodeState = { lastMs: 0, counter: 0 };

/** Fixed per-process session ID (descending encoding), stamped on every request. */
const SESSION_ID = opencodeCreate("ses", true);

// Load the injected tls-client shared library (OPENCODE_TLS_LIBRARY) once at
// boot; node-tls-client's Client requires it before any request.
await initTLS();

/** The opencode CLI's BoringSSL ClientHello, captured from the real CLI. */
const JA3 =
  "771,1301,1302,1303,c02b,c02f,c02c,c030,cca9,cca8,c009,c013,c00a,c014,9c,9d,2f,35,17,ff01,a,b,23,10,5,d,12,33,2d,2b,1d,17,18,0";

const USER_AGENT =
  "opencode/1.18.18 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14";
const ACCEPT_ENCODING = "gzip, deflate, br, zstd";

const originalFetch = globalThis.fetch;

/**
 * Port of opencode's ID generator (packages/opencode/src/id/id.ts):
 * monotonic per-millisecond counter folded into a 48-bit time+counter value,
 * optionally descending (bitwise-NOT), hex-encoded to 6 bytes, padded with
 * random base62 to a 26-char total (`<prefix>_<12 hex><14 base62>`).
 */
function opencodeCreate(prefix, descending) {
  const ms = Date.now();
  opencodeState.lastMs === ms
    ? opencodeState.counter++
    : ((opencodeState.lastMs = ms), (opencodeState.counter = 0));
  const counter = opencodeState.counter;
  // Fold the 48-bit time+counter (id.ts create()). JS bitwise ops are 32-bit,
  // so truncate with modulo and take the 48-bit complement via subtraction.
  let v = (ms * 0x1000 + counter) % 0x1000000000000;
  if (descending) v = 0xffffffffffff - v;
  const hexPart = v.toString(16).padStart(12, "0");
  const chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
  const random = Array.from(crypto.getRandomValues(new Uint8Array(14)))
    .map((b) => chars[b % 62])
    .join("");
  return `${prefix}_${hexPart}${random}`;
}

/** Wrap a node-tls-client string body into a fetch-compatible Response. */
function toResponse(status, headers, body) {
  const record = {};
  for (const [name, value] of Object.entries(headers)) {
    if (value !== undefined) record[name] = value;
  }
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    },
  });
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(record),
    body: stream,
    async text() {
      return body;
    },
    async json() {
      return JSON.parse(body);
    },
  };
}

/**
 * Send one opencode-Zen request through node-tls-client with the CLI's JA3
 * fingerprint and headers. node-tls-client is non-streaming, so the SSE body
 * arrives whole and is exposed as a ReadableStream; dsh's SSE parser consumes
 * it unchanged.
 */
async function zenFetch(url, init) {
  const headers = new Headers(init?.headers);
  // Drop any attribution/dsh canonical-cased copies; lowercase keys win.
  for (const name of [
    "user-agent",
    "accept-encoding",
    "x-opencode-client",
    "x-opencode-project",
    "x-opencode-request",
    "x-opencode-session",
  ]) {
    headers.delete(name);
  }
  headers.set("User-Agent", USER_AGENT);
  headers.set("Accept", "*/*");
  headers.set("Accept-Encoding", ACCEPT_ENCODING);
  headers.set("x-opencode-client", "cli");
  headers.set("x-opencode-project", "global");
  headers.set("x-opencode-request", opencodeCreate("msg", false));
  headers.set("x-opencode-session", SESSION_ID);

  const session = new Session({ ja3string: JA3 });
  try {
    const response = await session.post(String(url), {
      headers: Object.fromEntries(headers.entries()),
      body: init?.body,
      timeout: init?.signal?.timeout,
    });
    return toResponse(response.status, response.headers, response.body);
  } finally {
    await session.close();
  }
}

globalThis.fetch = async (input, init) => {
  const url = String(input);
  return url.includes(ZEN_BASE) ? zenFetch(url, init) : originalFetch(input, init);
};
