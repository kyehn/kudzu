import { setupDroid, setupReasonix, setupDirac, loadBootstrapState } from "./proxy.js";
import { isFreeModelId } from "./models.js";

const PORT = 3456;
const UPSTREAM = "https://opencode.ai/zen";

interface CLIOptions {
  port: number;
  setup: boolean;
  agents: string[];
  help: boolean;
}

function parseArgs(argv: string[]): CLIOptions {
  const opts: CLIOptions = { port: PORT, setup: false, agents: ["droid", "reasonix", "dirac"], help: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--help" || a === "-h") opts.help = true;
    else if (a === "--port" && argv[i + 1]) opts.port = parseInt(argv[++i], 10);
    else if (a === "--setup") opts.setup = true;
    else if (a === "--agents" && argv[i + 1]) opts.agents = argv[++i].split(",").map((s) => s.trim().toLowerCase());
  }
  return opts;
}

const HELP = `opencode-zen-proxy

Usage:
  node index.js [options]

Options:
  --port <n>         Listen port                 (default: 3456)
  --setup            Write agent config files and exit
  --agents <list>    Comma-separated agents for --setup
                     (default: droid,reasonix,dirac)
  --help             Show this help
`;

async function main(): Promise<void> {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) {
    console.log(HELP);
    process.exit(0);
  }

  console.log("📡 Fetching upstream model list...");
  const { modelIds, modelsDevInfo } = await loadBootstrapState();
  const freeModels = modelIds.filter(isFreeModelId);
  console.log(`   Found ${modelIds.length} upstream models, ${freeModels.length} free`);

  if (opts.setup) {
    console.log("\n📝 Writing agent configs...");
    if (opts.agents.includes("droid")) {
      await setupDroid(opts.port, modelIds, modelsDevInfo);
      console.log(`  ✅ Droid: ~/.factory/settings.json`);
    }
    if (opts.agents.includes("reasonix")) {
      await setupReasonix(opts.port, modelIds, modelsDevInfo);
      console.log(`  ✅ Reasonix: ~/.reasonix/config.toml`);
    }
    if (opts.agents.includes("dirac")) {
      await setupDirac(opts.port, modelIds, modelsDevInfo);
      console.log(`  ✅ Dirac: ~/.config/dirac/proxy.env`);
    }
    console.log("\n✅ Done. Config files written.");
    return;
  }

  // For running the proxy, just run the proxy module directly
  console.log("\n🚀 Starting proxy server...");
  await import("./proxy.js");
}

main().catch((e) => { console.error("Fatal:", e); process.exit(1); });