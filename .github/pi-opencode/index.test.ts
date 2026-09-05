/** Minimal tests: node:test + type stripping, no framework. */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
	buildModelConfig,
	isKnownZenBaseUrl,
	resolveEndpoint,
} from "./index.ts";

describe("buildModelConfig", () => {
	it("passes a catalog thinkingLevelMap through untouched", () => {
		const cfg = buildModelConfig(
			"muse-spark-1.3-contributor-free",
		) as unknown as {
			thinkingLevelMap: Record<string, string | null>;
		};
		assert.equal(cfg.thinkingLevelMap["xhigh"], "xhigh");
		assert.equal(cfg.thinkingLevelMap["max"], null);
	});
	it("omits thinkingLevelMap when the catalog declares none", () => {
		// big-pickle 在目录中无此字段 (有表透传/无表缺席, 上一用例对照);
		// 伪造能力表只会让缺省请求偏离 CLI (多发 reasoning_effort),
		// 故必须缺席而非捏造。
		const cfg = buildModelConfig("big-pickle") as unknown as Record<
			string,
			unknown
		>;
		assert.ok(!("thinkingLevelMap" in cfg));
	});
});

describe("resolveEndpoint", () => {
	it("throws on unregistered ids instead of guessing a wire", () => {
		assert.throws(
			() => resolveEndpoint("definitely-not-a-model-xyz"),
			/was never registered/,
		);
	});
	it("returns the registered per-model api", () => {
		buildModelConfig("big-pickle");
		assert.equal(resolveEndpoint("big-pickle"), "openai-completions");
	});
});

describe("isKnownZenBaseUrl", () => {
	it("accepts both live zen roots", () => {
		assert.equal(isKnownZenBaseUrl("https://opencode.ai/zen/v1"), true);
		assert.equal(isKnownZenBaseUrl("https://opencode.ai/zen"), true);
	});
	it("rejects unknown roots so drift is loud", () => {
		assert.equal(isKnownZenBaseUrl("https://example.com/v1"), false);
	});
});

describe("streamOpencodeZen", () => {
	it("缺省不补 effort: 只加 wire 身份, 不改写透传选项", async () => {
		// 经默认 export 拿到真实注册的 streamSimple, 用 onPayload 在网络前
		// 截获 params: 缺省/off 的 reasoning 必须不带 reasoning_effort
		// (CLI 同形), 否则就是旧 always-thinks 式补丁回潮, 本用例负责拦下。
		const mod = await import("./index.ts");
		let registered!: {
			streamSimple: (...args: never[]) => AsyncIterable<unknown>;
		};
		await mod.default({
			registerProvider(_id: string, cfg: unknown) {
				registered = cfg as typeof registered;
			},
		} as never);
		const model = {
			provider: "opencode",
			...(mod.buildModelConfig("big-pickle") as unknown as Record<
				string,
				unknown
			>),
			api: "openai-completions",
			baseUrl: "https://opencode.ai/zen/v1",
		};
		const context = {
			messages: [{ role: "user", content: "hi" }],
			tools: [],
		};
		async function wireParams(
			reasoning: string | undefined,
		): Promise<Record<string, unknown> | null> {
			let seen: Record<string, unknown> | null = null;
			try {
				for await (const _ of registered.streamSimple(
					model as never,
					context as never,
					{
						apiKey: "public",
						reasoning: reasoning as never,
						sessionId: "probe",
						async onPayload(p: unknown) {
							seen = p as Record<string, unknown>;
							throw new Error("probe-stop");
						},
					} as never,
				)) {
					/* drain */
				}
			} catch (e) {
				if ((e as Error).message !== "probe-stop") throw e;
			}
			return seen;
		}
		assert.ok(!("reasoning_effort" in (await wireParams(undefined))!));
		assert.ok(!("reasoning_effort" in (await wireParams("off"))!));
	});
});
