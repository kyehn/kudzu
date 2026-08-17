// 构建期注入：把 opencode 客户端模拟装配进 pi-ai 的 openai-completions api。
// 用法: node inject.mjs <pi-ai>/dist/api/openai-completions.js
// 幂等：已注入则直接退出 0；任何 anchor 未命中都以非零退出（不静默成功）。
import { cpSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const target = process.argv[2];
const simPath = process.argv[3] ?? join(HERE, "opencode-sim.mjs");
if (!target) {
  console.error("usage: node inject.mjs <pi-ai>/dist/api/openai-completions.js [opencode-sim.mjs]");
  process.exit(2);
}

const src = readFileSync(target, "utf8");
if (src.includes("opencode-sim")) {
  console.log("opencode-sim: already injected, skipping");
  process.exit(0);
}

const sim = readFileSync(simPath, "utf8");
if (!sim.includes("OPENCODE_USER_AGENT")) {
  console.error("opencode-sim.mjs broken (missing marker)");
  process.exit(1);
}
cpSync(simPath, join(dirname(target), "opencode-sim.mjs"));

// anchors（与 pi-ai dist/api/openai-completions.js 的既定形状逐字节匹配）
const IMPORT_ANCHOR = 'import OpenAI from "openai";';
const MERGE_ANCHOR = `    // Merge options headers last so they can override defaults
    if (optionsHeaders) {
        Object.assign(headers, optionsHeaders);
    }
    return new OpenAI({`;
const OPENAI_ANCHOR = `        dangerouslyAllowBrowser: true,
        defaultHeaders: headers,
    });`;

for (const [name, anchor] of [
  ["import", IMPORT_ANCHOR],
  ["merge", MERGE_ANCHOR],
  ["openai", OPENAI_ANCHOR],
]) {
  if (src.split(anchor).length !== 2) {
    console.error(`opencode-sim: ${name} anchor not uniquely matched`);
    process.exit(1);
  }
}

const patched = src
  .replace(
    IMPORT_ANCHOR,
    IMPORT_ANCHOR +
      '\nimport { opencodeFactoryFetch, opencodeSimHeaders } from "./opencode-sim.mjs";',
  )
  .replace(
    MERGE_ANCHOR,
    `    // Merge options headers last so they can override defaults
    if (optionsHeaders) {
        Object.assign(headers, optionsHeaders);
    }
    if (headers["x-opencode-client"] || headers["x-opencode-project"]) {
        Object.assign(headers, opencodeSimHeaders(headers));
    }
    return new OpenAI({`,
  )
  .replace(
    OPENAI_ANCHOR,
    `        dangerouslyAllowBrowser: true,
        defaultHeaders: headers,
        fetch: opencodeFactoryFetch(),
    });`,
  );

for (const marker of ["opencode-sim.mjs", "opencodeFactoryFetch()", 'opencodeSimHeaders(headers)']) {
  if (!patched.includes(marker)) {
    console.error(`opencode-sim: marker "${marker}" missing after patch`);
    process.exit(1);
  }
}
writeFileSync(target, patched);
console.log(`opencode-sim: injected into ${target}`);