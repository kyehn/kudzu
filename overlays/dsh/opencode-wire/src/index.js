import { PiAiAdapter, Config } from "@deepseek-ai/dsh-llm-pi-ai";
import { launchEnvironmentOf } from "@deepseek-ai/dsh-launch-environment";
import { createModels } from "@earendil-works/pi-ai";
import {
  builtinProviders,
  getBuiltinModels,
} from "@earendil-works/pi-ai/providers/all";

const OPENCODE_VERSION = "1.18.32";
const BUN_VERSION = "1.3.14";
const USER_AGENTS = {
  openai: `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.23 runtime/bun/${BUN_VERSION}`,
  "openai-responses": `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.40 runtime/bun/${BUN_VERSION}`,
  anthropic: `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.46 runtime/bun/${BUN_VERSION}`,
};

const ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

const sequence = { counter: 0, lastMs: 0 };

function nextPacked(nowMs) {
  if (nowMs !== sequence.lastMs) {
    sequence.lastMs = nowMs;
    sequence.counter = 0;
  }
  sequence.counter += 1;
  return (nowMs * 0x1000 + sequence.counter) & 0xffffffffffff;
}

// opencode `iC()`, byte for byte: six bytes of
// `Date.now() * 0x1000 + counter` from the low 48 bits (bit-inverted in full
// for a descending id) as 12 hex chars, then 14 base62 chars from the CSPRNG.
function identifier({ descending }) {
  const packed = nextPacked(Date.now());
  const value = descending ? ~packed & 0xffffffffffff : packed;
  const scope = value.toString(16).padStart(12, "0");
  let suffix = "";
  const bytes = new Uint32Array(14);
  crypto.getRandomValues(bytes);
  for (const byte of bytes) suffix += ALPHABET[byte % 62];
  return scope + suffix;
}

function newSessionId() {
  return `ses_${identifier({ descending: true })}`;
}

const PROTOCOL_API = {
  openai: "openai-completions",
  "openai-responses": "openai-responses",
  anthropic: "anthropic-messages",
};

// Routes are `${models.dev provider}-${protocol}`; the protocol decides both
// the wire UA pin and the pi-ai api implementation a served model uses.
function routeProtocol(route) {
  const protocol = route.split("-").slice(1).join("-");
  if (protocol in PROTOCOL_API) return protocol;
  throw new Error(`opencode-wire: route "${route}" names no known protocol`);
}

// Minted per request, so nothing here is a stored header value: the request id
// changes every call, the session id changes when the caller opens a session.
function wireHeaders(protocol, sessionId) {
  const headers = {
    "x-opencode-client": "cli",
    "x-opencode-project": "global",
    "x-opencode-session": sessionId,
    "x-opencode-request": `msg_${identifier({ descending: false })}`,
  };
  if (protocol in USER_AGENTS) headers["User-Agent"] = USER_AGENTS[protocol];
  return headers;
}

const catalogProviders = new Map(
  builtinProviders().map((provider) => [provider.id, provider]),
);

// providers-config.py carries the models.dev `api` endpoint; the installed
// catalog entry stays the fallback so a route without one still dispatches.
function baseUrlOf(source, fallback) {
  return source.baseURL ?? fallback.baseUrl;
}

function wireProvider(route, source) {
  const provider = route.split("-")[0];
  const protocol = routeProtocol(route);
  const base = catalogProviders.get(provider);
  if (base === undefined) {
    throw new Error(`opencode-wire: route "${route}" has no pi-ai catalog provider`);
  }
  const catalog = getBuiltinModels(provider);
  const scriptById = new Map(
    (source.models ?? []).map((model) => [model.id ?? model, model]),
  );
  const materialized = [];
  for (const [id, override] of scriptById) {
    const sibling =
      catalog.find((model) => model.id === id) ??
      catalog.find((model) => model.api === PROTOCOL_API[protocol]);
    if (sibling === undefined) {
      throw new Error(
        `opencode-wire: route "${route}" lists model "${id}" that the installed pi-ai catalog cannot dispatch over ${protocol}`,
      );
    }
    materialized.push({
      ...sibling,
      id,
      // pi-ai resolves a request's provider from each model's own `provider`
      // field, so every served model carries the ROUTE, not the catalog id
      // (a catalog id here fails the dispatch with `Unknown provider`). The
      // sibling supplies only the wire protocol and its base URL.
      provider: route,
      baseUrl: baseUrlOf(source, sibling),
      name: override.name ?? id,
      ...(override.contextWindow === undefined
        ? {}
        : { contextWindow: override.contextWindow }),
      ...(override.maxTokens === undefined
        ? {}
        : { maxTokens: override.maxTokens }),
      ...(override.input === undefined ? {} : { input: override.input }),
    });
  }
  return {
    ...base,
    id: route,
    name: route,
    baseUrl: baseUrlOf(source, base),
    auth: {
      ...base.auth,
      apiKey: {
        name: route,
        resolve: ({ credential }) =>
          Promise.resolve({
            auth: credential?.key === undefined ? {} : { apiKey: credential.key },
            source: "opencode-wire",
          }),
      },
    },
    getModels: () => materialized,
  };
}

class WireAdapter extends PiAiAdapter {
  profileOf(snapshot, provider) {
    const profile = super.profileOf(snapshot, provider);
    return {
      ...profile,
      headers: profile.headers ?? {},
      modelErrors: profile.modelErrors ?? new Map(),
      configuredMaxTokens: profile.configuredMaxTokens ?? new Map(),
    };
  }

  async *streamWithSnapshot(options, snapshot) {
    const profile = this.profileOf(snapshot, options.provider);
    const headers = wireHeaders(
      routeProtocol(options.provider),
      options.sessionId ?? newSessionId(),
    );
    yield* super.streamWithSnapshot(
      { ...options, sessionId: options.sessionId ?? headers["x-opencode-session"] },
      {
        ...snapshot,
        profiles: new Map(snapshot.profiles).set(options.provider, {
          ...profile,
          headers: { ...profile.headers, ...headers },
        }),
      },
    );
  }

  current() {
    const profiles = this.config.profiles();
    if (this.snapshot?.profiles === profiles) return this.snapshot;
    const models = createModels(this.config.auth);
    for (const [route, source] of profiles) {
      models.setProvider(wireProvider(route, source));
    }
    this.snapshot = { profiles, models };
    return this.snapshot;
  }
}

const name = "opencode-wire";
const inject = ["llm"];

function apply(ctx, config) {
  const readProviders = () => {
    const field = config.providers;
    return (typeof field?.get === "function" ? field.get() : field) ?? {};
  };
  const profiles = () => {
    const parsed = Config({ providers: readProviders() });
    const field = parsed.providers;
    const raw = typeof field?.get === "function" ? field.get() : field;
    return new Map(Object.entries(raw ?? {}));
  };
  // The harness credential seam, verbatim from llm-pi-ai: the stored record
  // first, then the launch environment (process env, $DSH_HOME/.env, project
  // .env). No plugin-owned environment names.
  const resolveApiKey = async (provider, profile) => {
    const ref = profile.apiKeyEnv;
    if (ref === undefined) return undefined;
    const credentials = ctx.get("credentials");
    const hit =
      credentials !== undefined
        ? (await credentials.resolve(ref))?.value
        : launchEnvironmentOf(ctx).get(ref)?.value;
    if (hit !== undefined && hit.length > 0) return hit;
    throw new Error(
      `opencode-wire: no credential for route "${provider}" (${ref} unset)`,
    );
  };
  const adapter = new WireAdapter({
    profiles,
    resolveApiKey,
    auth: { credentials: undefined, authContext: undefined },
  });
  let registration;
  const sync = () => {
    const routes = [...profiles().keys()];
    if (registration === undefined) {
      if (routes.length === 0) return;
      registration = ctx.llm.registerAdapter(routes, adapter);
    } else {
      registration.replace(routes);
    }
  };
  sync();
  ctx.on("loader/volatile-update", () => {
    try {
      sync();
    } catch (error) {
      ctx.logger.error("opencode-wire: route registration conflicts");
      ctx.logger.error(error);
    }
  });
}

export { apply, inject, name };
