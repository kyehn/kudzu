/** Minimal tests: node:test + type stripping, no framework. */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
	buildModelConfig,
	isKnownZenBaseUrl,
	resolveEndpoint,
	translateAlwaysThinksReasoning,
} from "./index.ts";

describe("translateAlwaysThinksReasoning", () => {
	it("maps missing level to low", () => {
		assert.equal(translateAlwaysThinksReasoning(undefined), "low");
	});
	it("keeps max on max (xhigh maps to null and gets dropped by the adapter)", () => {
		assert.equal(translateAlwaysThinksReasoning("max"), "max");
	});
	it("passes other levels through", () => {
		assert.equal(translateAlwaysThinksReasoning("high"), "high");
		assert.equal(translateAlwaysThinksReasoning("low"), "low");
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

describe("buildModelConfig", () => {
	it("gives big-pickle an always-thinks map with a usable max", () => {
		const cfg = buildModelConfig("big-pickle") as unknown as {
			thinkingLevelMap: Record<string, string | null>;
		};
		assert.equal(cfg.thinkingLevelMap["max"], "max");
		assert.equal(cfg.thinkingLevelMap["low"], "low");
		assert.equal(cfg.thinkingLevelMap["high"], "high");
		assert.equal(cfg.thinkingLevelMap["xhigh"], null);
	});
});
