import { homedir } from "node:os";
import { join } from "node:path";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { parse as parseToml, stringify as stringifyToml } from "@iarna/toml";
import { parse as parseJson, stringify as stringifyJson } from "comment-json";

import { ModelsDevModelInfo, isFreeModelId } from "./models.js";

export async function setupDroid(port: number, models: string[], modelsDev: Record<string, ModelsDevModelInfo>): Promise<void> {
  const cfgPath = join(homedir(), ".factory", "settings.json");
  await mkdir(join(homedir(), ".factory"), { recursive: true });

  let existing: any = { customModels: [] };
  try {
    const content = await readFile(cfgPath, "utf8");
    existing = parseJson(content, null, true);
  } catch {}

  if (!Array.isArray(existing.customModels)) existing.customModels = [];

  const freeModels = models.filter(isFreeModelId);
  // Remove ALL old entries for these model IDs (by model field)
  const modelIdsSet = new Set(freeModels);
  existing.customModels = existing.customModels.filter((m: any) => !modelIdsSet.has(m.model));

  for (const id of freeModels) {
    const info = modelsDev[id] || {};
    const entry = {
      model: id,
      displayName: id,
      baseUrl: `http://127.0.0.1:${port}/v1`,
      apiKey: "public",
      provider: "generic-chat-completion-api",
      maxOutputTokens: info.limit?.output ?? 4096,
    };
    existing.customModels.push(entry);
  }

  await writeFile(cfgPath, stringifyJson(existing, null, 2) + "\n");
}

export async function setupReasonix(port: number, models: string[], modelsDev: Record<string, ModelsDevModelInfo>): Promise<void> {
  const cfgPath = join(homedir(), ".reasonix", "config.toml");
  await mkdir(join(homedir(), ".reasonix"), { recursive: true });

  let existing: any = { providers: [] };
  try {
    const content = await readFile(cfgPath, "utf8");
    existing = parseToml(content);
  } catch {}

  if (!Array.isArray(existing.providers)) existing.providers = [];

  const freeModels = models.filter(isFreeModelId);
  // Remove ALL old entries for these model IDs
  const modelIdsSet = new Set(freeModels);
  existing.providers = existing.providers.filter((p: any) => !modelIdsSet.has(p.name) && !modelIdsSet.has(p.model));

  for (const id of freeModels) {
    const info = modelsDev[id] || {};
    existing.providers.push({
      name: id,
      kind: "openai",
      base_url: `http://127.0.0.1:${port}/v1`,
      api_key: "public",
      model: id,
      context_window: info.limit?.context ?? 128_000,
    });
  }

  await writeFile(cfgPath, stringifyToml(existing));
}

export async function setupDirac(port: number, models: string[], _modelsDev: Record<string, ModelsDevModelInfo>): Promise<void> {
  const cfgDir = join(homedir(), ".config", "dirac");
  await mkdir(cfgDir, { recursive: true });
  const envPath = join(cfgDir, "proxy.env");
  const freeModels = models.filter(isFreeModelId);
  const content = [
    "# opencode-zen proxy env — source this before running dirac",
    "# Usage: source " + envPath + " && dirac",
    `export OPENAI_API_BASE="http://127.0.0.1:${port}/v1"`,
    `export OPENAI_API_KEY="public"`,
    `export OPENAI_BASE_URL="http://127.0.0.1:${port}/v1"`,
    `# Default model (override with: dirac -m <model>)`,
    `export DIRAC_MODEL="${freeModels[0] || ""}"`,
  ].join("\n") + "\n";
  await writeFile(envPath, content);
}