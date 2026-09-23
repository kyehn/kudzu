# Tool integration research — 2026-09

First-party research across five topics: npm versions/install docs for the six CLI/ACP
packages used by this repo, `kyehn/kudzu` main-branch history, Paseo ACP provider
configuration and daemon-less testing, opencode model-list/live-gateway derivation, and the
pi-opencode dual-host extension contract.

**Research date:** 2026-09-24 (UTC).
**Repo state referenced:** `kyehn/kudzu` `main` tip
`d5c297c35598f74d9bfbd2ec4566a5c516606276` (2026-09-24T22:05:49Z, per
`.git/refs/heads/main` and the commits feed).

**Method / session constraints (read first):**

- The sandbox shell in this session was unusable (`bash` failed with
  `Cannot find module '/usr/local/lib/node_modules/deepseekharness-acp-interactive/node_modules/@deepseek-ai/dsh-subprocess-local/lib/runner.js'`),
  so no `git status/diff`, no `npm view`, no CLI `--help`, no local hash comparison.
  All version/history facts come from HTTP first-party sources (npm registry, GitHub
  `commits/*.atom` + `commit/<sha>.patch`, `raw.githubusercontent.com`, jsDelivr,
  `paseo.sh`, `opencode.ai`, project sites). `web_search` was unavailable (HTTP 401) and
  `api.github.com` was rate-limited (HTTP 403); GitHub was read via feeds/patches/raw.
- Publish times are derived from the registry's `_npmOperationalInternal.tmp` epoch-ms
  prefix — treat them as "registry operational timestamp ≈ publish time".
- Facts that could not be confirmed from a primary source are labeled **UNVERIFIED**.

---

## 1. npm latest versions + official install/docs

### 1.1 Version table (registry, fetched 2026-09-24)

| Package | dist-tags (latest / other) | Publish timestamp of latest (UTC) | bin | engines | official repo |
|---|---|---|---|---|---|
| `reasonix` | `latest` **1.39.0** | 2026-09-24T17:00:15Z | `reasonix` → `bin/reasonix.js` | `node >=18` | github.com/esengine/DeepSeek-Reasonix |
| `@getpaseo/cli` | `latest` **0.9.2**, `beta` 0.9.2 | 2026-09-24T10:15:53Z | `paseo` → `bin/paseo` | — | github.com/getpaseo/paseo |
| `@earendil-works/pi-coding-agent` | `latest` **0.87.1**, `legacy-node20` 0.74.2 | 2026-09-22T19:42:48Z | `pi` → `dist/bundle/cli.js` | `node >=22.19.0` | github.com/earendil-works/pi (`packages/coding-agent`) |
| `@oh-my-pi/pi-coding-agent` | `latest` **18.3.0** | 2026-09-24T02:31:39Z | `omp` → `dist/cli.js` | `bun >=1.3.14` | github.com/can1357/oh-my-pi (homepage `https://omp.sh`) |
| `deepseekharness-acp-interactive` | `latest` **1.3.2** | 2026-09-24T01:10:39Z | `dsh-acp-interactive` → `lib/bin.js` | `^22.19.0 \|\| >=24.0.0` | github.com/ClickPM/dsh-acp-interactive |
| `@opencode/cli` | `latest` **2.0.16**, `beta` 0.0.0-beta-19507, `dev` 0.0.0-dev-20142 | 2026-09-24T06:32:20Z | `opencode`, `opencode2` → `bin/opencode.exe` | — | github.com/anomalyco/opencode |
| `opencode-ai` (docs' npm package, see 1.3) | `latest` **1.18.32** | 2026-09-21T22:50:42Z | `opencode` → `bin/opencode.exe` | — | github.com/anomalyco/opencode |

Registry endpoints used (first-party, verbatim):
`https://registry.npmjs.org/<pkg>/latest`, `https://registry.npmjs.org/<pkg>/<version>`,
`https://registry.npmjs.org/-/package/<name>/dist-tags` (scope encoded as `@scope%2Fpkg`).

Notable metadata details:

- `reasonix@1.39.0`: `unpackedSize` 14,370 bytes, `fileCount` 3, thin launcher with
  `optionalDependencies` on `@reasonix/cli-{linux,win32,darwin}-{x64,arm64}@1.39.0`
  (platform binaries, same pattern as opencode); `gitHead` `6845b6de…`; built/published
  with npm 10.9.8 on Node 22.23.2; SLSA provenance attestations present.
- `@opencode/cli`: per-platform optional dependencies; `postinstall`-driven binary wrapper.
- `@oh-my-pi/pi-coding-agent`: **Bun-only** — `engines.bun >= 1.3.14`; Node is not a
  supported runtime for the `omp` CLI.
- `@earendil-works/pi-coding-agent`: Node `>=22.19.0`; the `legacy-node20` dist-tag (0.74.2)
  is the line for older Node.

### 1.2 Official install commands (from project docs/READMEs)

```bash
# Paseo CLI — https://paseo.sh/docs.md ("Server / CLI")
npm install -g @getpaseo/cli     # then run: paseo
# also: Homebrew/desktop app/Docker (ghcr.io/getpaseo/paseo:latest)

# pi (Earendil) — packument bin `pi`; docs https://pi.dev/docs/latest (Quickstart: /docs/latest/quickstart)
npm install -g @earendil-works/pi-coding-agent
# repository supply-chain note: upstream recommends --ignore-scripts installs

# OMP (Oh My Pi) — https://raw.githubusercontent.com/can1357/oh-my-pi/main/README.md
curl -fsSL https://omp.sh/install | sh          # macOS/Linux
brew install can1357/tap/omp                    # Homebrew
bun install -g @oh-my-pi/pi-coding-agent        # Bun (recommended; bun >= 1.3.14)
nix profile install github:can1357/oh-my-pi     # Nix
irm https://omp.sh/install.ps1 | iex            # Windows

# OpenCode — https://opencode.ai/docs/ ("Install")
curl -fsSL https://opencode.ai/install | bash
npm install -g opencode-ai                      # docs' npm package = v1 line (1.18.32)
brew install anomalyco/tap/opencode
# Windows: choco install opencode | scoop install opencode | mise use -g github:anomalyco/opencode
# kudzu instead uses the v2 line: npm install -g @opencode/cli (2.0.16)

# dsh ACP provider — https://raw.githubusercontent.com/ClickPM/dsh-acp-interactive/main/README.md
npm install --global deepseekharness-acp-interactive
dsh-acp-interactive --setup                     # stores DEEPSEEK_API_KEY via the harness credential store

# reasonix — https://raw.githubusercontent.com/esengine/reasonix/main/README.md
npm install -g reasonix                         # also installs a `dsnix` alias; package declares engines.node >= 18 (README's Node 24+/pnpm 10 requirement is for building the desktop app)
npx reasonix code                               # one-shot, no global install
```

### 1.3 Official docs pages (URLs)

- Paseo: `https://paseo.sh/docs.md` (getting started),
  `https://paseo.sh/docs/cli.md` (CLI reference), `https://paseo.sh/docs/custom-providers.md`,
  `https://paseo.sh/docs/providers.md`, `https://paseo.sh/docs/supported-providers.md`,
  `https://paseo.sh/docs/troubleshooting.md`, index `https://paseo.sh/llms.txt`.
- pi: `https://pi.dev/docs/latest` (+ `/docs/latest/quickstart`, `/docs/latest/cli`,
  `/docs/latest/extensions`, `/docs/latest/custom-provider`), repo README
  `https://raw.githubusercontent.com/earendil-works/pi/main/README.md`.
- OMP: `https://omp.sh`, repo README (URL above), `https://omp.sh/docs/providers`,
  `https://omp.sh/docs/tools`.
- OpenCode: `https://opencode.ai/docs/`, `/docs/models/`, `/docs/providers/`, `/docs/zen/`,
  `/docs/cli/`, config schema `https://opencode.ai/config.json`; repo
  `https://github.com/anomalyco/opencode`.
- dsh: repo README (URL above), behavior reference `docs/reference.en.md`,
  Zed compatibility matrix `docs/compatibility.en.md`, ACP registry PR
  `https://github.com/agentclientprotocol/registry/pull/585`.
- reasonix: repo README (URL above), guide `https://esengine.github.io/DeepSeek-Reasonix/configuration.html`,
  CLI reference `docs/CLI-REFERENCE.md`.

### 1.4 Version facts worth flagging

- **reasonix repo/README vs npm line:** the README at `esengine/reasonix` (mirror of
  `esengine/DeepSeek-Reasonix`) says the TypeScript line is "legacy (0.x), in maintenance
  mode" and that active development moved to the Go rewrite on branch `main-v2`. npm
  `latest` is 1.39.0 and ships platform binary packages (`@reasonix/cli-*`). Which branch
  produces 1.39.0 is **UNVERIFIED**; `gitHead 6845b6de` exists but was not mapped to a branch.
- **Two opencode npm lines:** official docs install `opencode-ai` (v1, latest 1.18.32);
  this repo installs `@opencode/cli` (v2, latest 2.0.16, bins `opencode` + `opencode2`).
  Both are published from `anomalyco/opencode`. The repo's wire-identity pins are anchored
  to `opencode/1.18.32` (see §4), while the local working tree's dsh generator uses
  `opencode/2.0.16` (see §2.3) — gateway acceptance of the v2 UA was UNVERIFIED at
  research time and is now confirmed working (§6.3, §8.2).
- `@getpaseo/cli` packument has **no `repository` field**; the origin is established by the
  docs (`https://github.com/getpaseo/paseo`) instead.

---

## 2. `kyehn/kudzu` main-branch history relevant to this work

Sources: `https://github.com/kyehn/kudzu/commits/main.atom`,
path feeds `https://github.com/kyehn/kudzu/commits/main/<path>.atom`, and
`https://github.com/kyehn/kudzu/commit/<sha>.patch`.

### 2.1 Timeline (2026-09-18 → 2026-09-24, main)

| Date (UTC) | SHA | Title / effect |
|---|---|---|
| 2026-09-18 | `6804bc6f` | nix 3.22.4 → 3.22.5 |
| 2026-09-19 | `f1faf3c8` | maki: init at 0.5.5 (reasonix→maki rename era) |
| 2026-09-22 07:26 | `817a653e` | reasonix: drop |
| 2026-09-22 07:30 | `812d2d8d` | dsh-acp-interactive: init at 1.3.0 |
| 2026-09-23 00:31 | `7a0c18a2` | dsh-acp-interactive: drop |
| 2026-09-23 08:48 | `29394b47` / `321ab026` | maki 0.5.5 → 0.5.6; "unstable" |
| 2026-09-23 15:09 | `a88731df` | pi-opencode: restore with `models-store.json` free-catalog merge (verified vs pi/pi-ai 0.87.1) |
| 2026-09-23 16:23 | `91787e35` | restore dsh/omp/pi wiring, align UA pins to `opencode 1.18.32`, `provider-utils 4.0.23/4.0.40/4.0.46`; re-enable `dsh`/`omp` providers in `paseo-config.json` |
| 2026-09-23 18:24 | `9177e3f3` | omp-opencode: gate snapshot catalog (`@oh-my-pi/pi-catalog` 18.2.6: 26 free) by live gateway ids (observed 26 → 8 registered) |
| 2026-09-23 18:41 | `5fe0b83d` | pi-opencode: own the store refresh via pi.dev catalog (etag, 4 h throttle, self-`publish`) |
| 2026-09-24 11:30 | `73890b96` / `faa541e0` | dsh: dynamic zen settings + auth env (`OPENCODE_PUBLIC`), reasonix install pinned 1.38.12; pi-opencode merged into one dual-host plugin (`omp-opencode` removed, `npm test` = node + bun) |
| 2026-09-24 11:49 | `1334d0da` | paseo: conversation smoke test after onboard (added `pi -p` + `paseo run` PONG loop) |
| 2026-09-24 15:42 | `071e06fd` | dsh: POST-probe model liveness (400 "Model is unavailable" dropped, 403 FreeTier kept → 7 alive models); smoke switched to `zen:mimo-v2.6-flash-free`, capture-before-grep to avoid SIGPIPE; maki added to smoke matrix |
| 2026-09-24 22:05 | `d5c297c3` (tip) | message says "ci: smoke maki auto-compaction against the Zen gate", **but the diff only deletes the 18-line conversation-smoke block** from `.github/workflows/paseo.yml` |

Path feeds used: `.github/pi-opencode.atom`, `.github/workflows/paseo.yml.atom`,
`.github/paseo-config.json.atom`, `.github/dsh/generate-settings.py.atom`,
`overlays/maki/providers-config.py.atom`.

**Tip-commit message/diff mismatch:** `d5c297c3`'s patch body
(https://github.com/kyehn/kudzu/commit/d5c297c35598f74d9bfbd2ec4566a5c516606276.patch)
contains only `18 deletions` (the `pi -p` / `paseo run` PONG conversation smoke added by
`1334d0da`+`071e06fd`); no auto-compaction step appears in the patch. Net effect: as of
main tip, **`.github/workflows/paseo.yml` has no post-onboard conversation smoke**. The
claimed maki auto-compaction smoke step was not found anywhere in the tip file
(**UNVERIFIED** — it may exist in a different workflow, but `.github/workflows/` was not
fully enumerated).

### 2.2 Key file states on GitHub main (tip `d5c297c3`)

- `.github/paseo-config.json` — `$schema: https://paseo.sh/schemas/paseo.config.v1.json`,
  `version: 1`; enabled ACP providers: `maki` (`command: ["maki","acp","--yolo"]`),
  `dsh` (`command: ["dsh-acp-interactive"]`, `env: {"OPENCODE_PUBLIC": "public"}`),
  `omp`, `opencode2` (`command: ["opencode","acp"]`); disabled: `copilot`, `codex`,
  `pi`, `opencode`, `claude`. Daemon: `enableTerminalAgentHooks: false`,
  `relay.enabled: true`, `mcp.enabled: false`, `features.webUi.enabled: false`.
- `.github/workflows/paseo.yml` (tip) — installs unpinned `@getpaseo/cli`,
  `@earendil-works/pi-coding-agent`, `@opencode/cli` and pins
  `@oh-my-pi/pi-coding-agent@18.2.6`, `deepseekharness-acp-interactive@1.3.0`,
  `reasonix@1.38.12`; runs `omp plugin install ./.github/pi-opencode`,
  `python3 .github/dsh/generate-settings.py`, `./.github/dsh/apply-headers-patch.sh`,
  `paseo onboard --relay --voice disable`, then `tail -f ~/.paseo/daemon.log`.
- `.github/dsh/generate-settings.py` (tip) — `USER_AGENT = "opencode/1.18.32
  ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14"`, `is_alive()` **fails open**
  (any non-400-unavailable HTTP error, and `URLError`/`TimeoutError`, count as alive).

### 2.3 Local working tree diverges from origin (important)

Two files differ between this checkout and `d5c297c3` on GitHub (verified by reading the
local files vs SHA-pinned `raw.githubusercontent.com/kyehn/kudzu/d5c297c…/…`):

| File | GitHub `d5c297c3` | Local working tree |
|---|---|---|
| `.github/workflows/paseo.yml` | `npm install --global --yes @getpaseo/cli` (unpinned), `… pi-coding-agent`, `… @opencode/cli`, `deepseekharness-acp-interactive@1.3.0`, `reasonix@1.38.12`, `open-websearch`, `@mobilenext/mobile-mcp` | pinned: `@getpaseo/cli@0.9.2`, `@earendil-works/pi-coding-agent@0.87.1`, `@oh-my-pi/pi-coding-agent@18.3.0`, `deepseekharness-acp-interactive@1.3.2`, `reasonix@1.39.0`, `@opencode/cli@2.0.16`, `open-websearch@2.1.11`, `@mobilenext/mobile-mcp@1.0.5` |
| `.github/dsh/generate-settings.py` | UA `opencode/1.18.32 …`; `is_alive` fails open (network error → alive) | UA `opencode/2.0.16 …`; `is_alive` fails closed (network error → dead; only `401/403/429/5xx` → alive) |

`.github/pi-opencode/package.json` was identical locally and on GitHub at research time
(`pi-opencode@0.4.0`); the working tree now carries `0.5.0` with `@oh-my-pi/*@18.3.0`
dependencies. A **full-tree local-vs-origin diff** could not run at research time (now
resolved via `git status/diff`); at minimum, the two files above were local modifications
(they were not in any commit reachable from main tip per the path feeds). Whoever prepared
this workspace apparently pre-pinned the exact latest npm versions from §1.

---

## 3. Paseo ACP provider configuration + testing without restarting the daemon

### 3.1 ACP provider configuration (source: `https://paseo.sh/docs/custom-providers.md`)

- All custom providers live under `agents.providers` in `~/.paseo/config.json`
  (`PASEO_HOME` default `~/.paseo`). Schema: `https://paseo.sh/schemas/paseo.config.v1.json`.
- ACP agents: `{"extends": "acp", "label": "...", "command": ["<bin>", "<args>…"]}`.
  "Paseo spawns the process, sends an `initialize` JSON-RPC request, and the agent reports
  its capabilities, modes, and models at runtime."
- `command` is an array (first element = binary) and fully replaces the default launch
  command. `env` injects environment variables (this repo: `OPENCODE_PUBLIC=public` for dsh).
- Provider IDs must match `/^[a-z][a-z0-9-]*$/`; every custom entry needs `extends`
  (a first-class provider id or `"acp"`) and `label`.
- Model list control: `models` replaces the list entirely; `additionalModels` merges with
  runtime-discovered ACP models; an entry with the same `id` as a discovered model updates
  it in place; `isDefault` marks the default. Other fields: `disallowedTools`,
  `paseoTools`, `enabled`, `order`.
- **Hot reload:** "Run `paseo reload` after editing the file. Provider changes apply to
  future launches **without restarting the daemon**."

### 3.2 CLI surface for local conversation/CLI testing (source: `https://paseo.sh/docs/cli.md`)

Verified commands (all talk to the running daemon; none require a daemon restart):

```bash
paseo run -q --provider <id> --model <model> --wait-timeout 5m "Reply with exactly: PONG"
paseo run --background --quiet --title <t> "task"     # returns id immediately
paseo ls [-a] [-g] [--json]                           # list agents; -q = ids only
paseo attach <id>                                     # stream output (Ctrl+C detaches)
paseo send <id> "follow-up task" [--no-wait]          # continue the same conversation
paseo logs <id> [--tail N] [-f] [--filter tools]      # timeline / transcript
paseo wait <id> [--timeout 60]                        # block until current task finishes
paseo provider diagnostic <id> [--json]               # command, PATH/shell, binaries, version, model count, status — same as Settings → Providers → Diagnostic
paseo agent mode <id> --list | <mode>                 # modes; `paseo agent detach <id>`
paseo permit ls|allow|deny                            # permission requests
paseo daemon status | reload | restart | stop | config set …
paseo --host <host:port|unix|offer-url> <cmd>         # target another daemon; PASEO_HOST works too
```

Reload semantics (exact): "`reload` validates the file, applies runtime-safe changes, and
reports `appliedPaths`, `restartRequiredPaths`, and `overrideControlledPaths`. **It never
implicitly restarts.**" → the canonical no-restart flow after editing `~/.paseo/config.json`
is `paseo reload`, then `paseo provider diagnostic <provider>` to confirm the command/models,
then a one-shot `paseo run … | paseo logs …` conversation probe.

### 3.3 How this repo smoke-tests conversations (CI pattern)

From `1334d0da` + `071e06fd` patches (later removed by `d5c297c3`, see §2.1):

```bash
out=$(pi -p --model opencode/mimo-v2.6-flash-free "Reply with exactly: PONG")
printf '%s\n' "$out" | grep -qx PONG          # direct pi smoke, bypassing paseo

for spec in \
  "omp opencode/mimo-v2.6-flash-free" \
  "dsh zen:mimo-v2.6-flash-free" \
  "opencode2 opencode/mimo-v2.6-flash-free" \
  "maki opencode-openai/mimo-v2.6-flash-free"; do
  provider=${spec%% *}; model=${spec#* }
  id=$(paseo run -q --provider "$provider" --model "$model" --wait-timeout 5m "Reply with exactly: PONG" 2>&1 | tail -1)
  transcript=$(paseo logs "$id" --tail 50 | sed 's/^\[[^]]*\] //')
  printf '%s\n' "$transcript" | grep -qx PONG
done
```

Operational lessons recorded in those commits: capture output **before** grepping (a
`grep -q` can SIGPIPE the producer under `pipefail` → EPIPE failure, run 35995321580);
`zen:big-pickle` degenerates into hundreds of `PONG` chunks (301 observed) so it cannot be
used for exact-line assertions; `zen:mimo-v2.6-flash-free` echoes exactly and is the CI
smoke model. `paseo run`'s `-q` prints the agent id on the last line (`| tail -1`).

dsh-side session config (no restart either): switch models via ACP
`session/set_config_option` (`configId: model`, `value: zen:<id>`), per
`.github/dsh/README.md`; the ACP default dsh model is `deepseek-official`, so paseo runs
must pass `--model zen:<id>` explicitly.

---

## 4. How opencode dynamic model lists and live gateway gating should be derived

### 4.1 What opencode itself does (sources: `https://opencode.ai/docs/models/`,
`https://opencode.ai/docs/providers/`, docs "Last updated: Sep 24, 2026")

- Model/provider metadata comes from the **AI SDK + models.dev** (75+ providers).
- Selection: `/models` picker; config `"model": "<provider_id>/<model_id>"`;
  loading priority at startup = 1) `--model`/`-m` flag, 2) config `model`,
  3) last used model, 4) first model by internal priority.
- Picker filtering: per-provider `blacklist` (hide listed ids) and `whitelist` (keep only
  listed ids); they compose (whitelist narrows, blacklist removes).
- Custom providers declare `provider.<id>.models.<model_id>`; model options/variants are
  configured there. Credentials from `/connect` land in `~/.local/share/opencode/auth.json`.
- Zen (`https://opencode.ai/zen`) is opencode's curated provider; docs describe
  `opencode/gpt-5.1-codex`-style ids.

### 4.2 The repo's live-gateway rule (the pattern to reuse)

Canonical rule, two layers in different files. The **models.dev catalog walk** lives in
`overlays/maki/providers-config.py` and `.github/dsh/generate-settings.py`; the
**pi-opencode extension** does not read models.dev at all — it gates against the live list,
takes deprecation from the pi.dev registry, and additionally enforces a permanent
retired-id set (below).

1. **Live list:** `GET https://opencode.ai/zen/v1/models` with an opencode wire identity —
   per surface: `opencode/1.18.32 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`
   (maki registry walk and the extension gate; maki uses `4.0.{23,40,46}` per endpoint)
   vs `opencode/2.0.16 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14` (dsh probes).
   This list is authoritative for *existence*, but **not** for deprecation: it still lists
   models.dev-deprecated ids, which is why `gateByLive()` also drops a permanent
   `RETIRED_ZEN_IDS` set (`deepseek-v4-flash-free`, `mimo-v2.5-free`, `jev-1.13-free`)
   on every path — offline included — and why dsh additionally probes liveness.
2. **Catalog intersection:** walk `https://models.dev/api.json` → `provider.opencode.models`
   and keep only ids that are (a) on the live list, (b) `cost.input == 0 && cost.output == 0`,
   (c) `tool_call !== false`, (d) `text` in input modalities, (e) `status != "deprecated"`,
   (f) not routed through
   `@ai-sdk/openai` / `@ai-sdk/anthropic` npm packages. The deprecated filter (added
   2026-09-25) is what drops `mimo-v2.5-free` — the gateway `/models` list still shows it,
   so the gateway alone can never be the catalog source. (maki + dsh only; the extension
   gets the same outcome from pi.dev's curated registry + the retired-id set.)
3. **Liveness probe (dsh only):** `POST https://opencode.ai/zen/v1/chat/completions` with
   `{"model": id, "messages":[…], "max_tokens": 4}` and `Authorization: Bearer public`.
   - `400` + `"Model is unavailable"` → drop the model (upstream retired it).
   - `403` FreeTier → **keep** (the model exists; the gateway gate only applies to the
     request context — e.g. empty-`tools` requests, see `d5c297c3` message).
   - GitHub main fails **open** on other errors/network failures; the local working tree
     fails **closed** (see §2.3).
4. **Never write an empty catalog** (`refusing to write an empty DSH model catalog`).
5. Limits/context come from models.dev (`limit.context` / `limit.output`, defaults
   200 000 / 32 000).

Observed results (verified 2026-09-25): `deepseek-v4-flash-free` dropped (models.dev
`deprecated` + 400 "Model is unavailable"), `mimo-v2.5-free` dropped (models.dev
`deprecated`), final dsh catalog = **6** models (the ground-truth 8 free +
non-deprecated minus the two `openai-responses` muse-spark models, which dsh's
provider-level `api` cannot route); `big-pickle` unsuitable for exact assertions.

### 4.3 Per-host gating in the extensions

- **`gateByLive()` (`shared.ts`)** — every candidate list (pi free models, omp catalog) is
  filtered against `GET /models` (4 s timeout). Rules: fetch/shape failure → fall back to
  the eligible free list (boot never depends on the network); ids not in the host catalog
  are never injected; if the intersection is empty, keep the input list; and a permanent
  `RETIRED_ZEN_IDS` set (`deepseek-v4-flash-free`, `mimo-v2.5-free`, `jev-1.13-free`) is
  enforced **before** any of that — the gateway still lists the first two, no registry is
  reachable when the offline snapshot fallback serves them, so this chokepoint is what
  guarantees they never surface on any path.
- **omp host (2026-09-25 redesign):** authoritative source = live pi.dev registry
  (`https://pi.dev/api/models/providers/opencode`, fetched fresh on every plugin load,
  4 s timeout); the bundled `@oh-my-pi/pi-catalog` `models.json` `opencode-zen` section is
  kept **only as offline fallback** when pi.dev is unreachable. Both paths are
  free-filtered + `gateByLive`. Observed: registry path yields exactly the ground-truth 8
  (deprecated ids never appear); previous snapshot path could serve stale ids
  (`deepseek-v4-flash-free`, `mimo-v2.5-free`).
- **pi host:** base = builtin `@earendil-works/pi-ai/providers/all` ∪ the catalog source,
  which is the extension's own **boot fetch** of
  `https://pi.dev/api/models/providers/opencode` (fetched in parallel with
  `getAgentDir()/models-store.json` at load, 4 s timeout, most recent success cached as an
  overlay for the session) when it returns fresh — a fresh registry supersedes the store
  (the store is the same pi.dev payload, only older); while the boot fetch fails, the
  freshness-gated store cache applies (`PI_CODING_AGENT_DIR` honored, `lastModified` must
  beat `getBuiltinModelDataGeneratedAt()`). The boot fetch is required because headless
  `pi -p` sessions never trigger the host's network refresh (`allowModelNetwork` is false
  outside the interactive model selector), so a model published after install (e.g.
  `space-bunny-free`) would otherwise never appear. `refreshModels` still mirrors the
  host's `withRemoteCatalog` (4 h throttle via `checkedAt` — preserved on the file-read
  fallback too, `If-None-Match`/304 revalidation, `context.publish({persist})`), and now
  also swaps the overlay to the freshly fetched registry.
- **dsh:** generated `~/.dsh/settings.yaml` (`DSH_SETTINGS` overrides the path) with
  provider `zen`, `api: openai-completions`, `baseURL: https://opencode.ai/zen/v1`,
  `apiKeyEnv: OPENCODE_PUBLIC`, opencode `x-opencode-*` headers with **algorithm-generated
  ids** (descending `ses_` + ascending `msg_`, freshly derived per settings write —
  mirrors `identifier()` in `shared.ts`; no hardcoded id in the repo), and the derived
  model list.

---

## 5. pi-opencode dual-host extension contract (pi + omp)

Package: `.github/pi-opencode/` — one package, two host entry points, shared wire logic.
(Both the local copy and GitHub `main` carry this content; `package.json` verified identical.)

### 5.1 `package.json` (v0.5.0, MIT, ESM)

```jsonc
"pi":  { "extensions": ["./pi.ts"] },        // pi host loads pi.ts
"omp": { "extensions": ["./omp.ts"] },       // omp host loads omp.ts
"dependencies":     { "@oh-my-pi/pi-ai": "18.3.0",
                      "@oh-my-pi/pi-catalog": "18.3.0",
                      "@oh-my-pi/pi-coding-agent": "18.3.0" },
"peerDependencies": { "@earendil-works/pi-ai": "*",
                      "@earendil-works/pi-coding-agent": "*" },
"devDependencies":  { "@types/node": "26.4.1", "typescript": "^7.0.2" },
"scripts": { "typecheck": "tsc --noEmit",
             "test": "node smoke.test.ts && bun smoke.test.ts" }
```

Install/verify (from CI and the extension README):

```bash
# pi host
cp -r .github/pi-opencode ~/.pi/agent/extensions/pi-opencode
( cd ~/.pi/agent/extensions/pi-opencode && npm install && npm run typecheck && npm test )
# omp host
omp plugin install ./.github/pi-opencode
# npm test runs the same smoke suite under node AND bun (bun must be on PATH)
```

### 5.2 `shared.ts` — host-neutral wire layer (imported verbatim by both entries)

- **Zen identity:** `ZEN_ORIGIN=https://opencode.ai/zen`, `BASE_URL=…/zen/v1`,
  `API_KEY=public`, `OPENCODE_VERSION=1.18.32`; per-endpoint UA pins
  (`openai-completions`→provider-utils `4.0.23`, `openai-responses`→`4.0.40`,
  `anthropic-messages`→`4.0.46`, all suffixed `runtime/bun/1.3.14`).
- **Endpoint allow-list:** `anthropic-messages | google-generative-ai | openai-completions |
  openai-responses`. A model whose `api` is not in `ENDPOINTS` is rejected —
  "a new api from the dynamic catalog must be added explicitly".
- **Header forge:** `opencodeHeaders(api)` emits per-endpoint `User-Agent`,
  `x-opencode-client: cli`, `x-opencode-project` (sha1 of `git-remote:<host>/<path>`, else
  cached `<common-dir>/opencode` file, else first root commit, else `global`),
  `x-opencode-session` (`ses_` + descending 26-char id, rotated on `session_start`),
  `x-opencode-request` (`msg_` + ascending id). `identifier(descending)` implements the
  exact opencode id algorithm (12 hex chars of `timestamp<<12|counter`, bitwise-NOT when
  descending, + 14 base62 random chars).
- **Fetch wrapper:** strips all `x-stainless-*` SDK telemetry headers and re-pins the UA.
- **Free-model rule:** `isFreeModel` requires **both** cost legs `=== 0` (same rule as
  `overlays/maki/providers-config.py`).
- **Endpoint registry:** `endpoints: Map<modelId, {api, baseUrl, compat}>` filled at
  registration; `resolveEndpoint` **throws** if a model was never registered
  ("refusing to guess the endpoint").
- **`gateByLive`:** live `/models` gate described in §4.3 (eligible list fail-open, 4 s;
  the permanent `RETIRED_ZEN_IDS` drop applies first, on every path).
- **Context repair (`sanitizeZenContext`):** drops issuer-bound reasoning payloads the
  gateway rejects with "was not issued to this caller" (`reasoning.encrypted` details,
  `encrypted_content` + cross-turn id; plaintext `summary` survives); converts redacted
  thinking blocks to text (or drops them if empty); repairs tool-call ids that sanitize to
  an empty part (gateway error `call_id length must be >= 1`) to deterministic
  `call_repaired_<sha1[:8]>`, keeping `|item` suffixes and toolResult pairing consistent.
- **`makeZenStreamer(streamSimple)`:** wraps either host's `streamSimple` — asserts
  `baseUrl` stayed under `ZEN_ORIGIN`, merges `opencodeHeaders`, installs the fetch wrapper,
  forces `model.api`/`baseUrl`/`compat` from the registry, and runs `sanitizeZenContext`.

### 5.3 `pi.ts` — pi (node) entry

- Catalog: builtin `getBuiltinModels("opencode")` from `@earendil-works/pi-ai/providers/all`
  (baseline + `generated-at` must come from the same module — the host aliases
  `providers/all` to its bundled copy) **∪** the pi.dev source: the boot fetch result when
  it returns fresh (it supersedes the store), otherwise the freshness-gated
  `models-store.json` cache (see §4.3), all passed through
  free-filter + `gateByLive`. Stored entries are re-validated field-by-field
  (id/name/reasoning/api/baseUrl/input/cost/limits) via shared `normalizeZenModel`;
  malformed → `console.warn` + skip; well-formed but paid-for-another-route → silent skip;
  bundled-catalog drift (wrong `baseUrl` or unknown `api`) → **throws loudly**.
- Registration: `pi.registerProvider("opencode", { baseUrl, apiKey, api:
  "openai-completions", streamSimple: makeZenStreamer(streamSimple), models, refreshModels })`.
  `refreshModels` mirrors the host's `withRemoteCatalog`: restore `context.stored`,
  revalidate against pi.dev every 4 h with etag/304, swap the registry overlay, and
  `context.publish({persist})` itself (the host never persists a shadowed provider).
- If the initial free list is empty the extension registers **nothing** (returns early).

### 5.4 `omp.ts` — omp (bun) entry

- Catalog: `loadFreeEntries(fetchImpl)` first fetches the pi.dev registry (shared
  `fetchRemoteCatalog`); on `fresh` with a non-empty list that registry **replaces** the
  bundled `@oh-my-pi/pi-catalog/models.json` `["opencode-zen"]` snapshot (snapshot used
  only when pi.dev is unreachable), then free-filter + `gateByLive`. Registry entries
  carry pi.dev's `thinkingLevelMap` (level → wire value, incl. `off`); snapshot entries
  carry `thinking: {mode, efforts}` directly — `buildModelConfig` converts the map into
  omp's `ThinkingConfig` over `THINKING_EFFORTS` (canonical order, `off` excluded), so the
  effort ladder survives either source. Exported for tests; stub-driven smoke asserts
  retired ids never survive (online and offline), new registry models appear, and the
  ladder converts.
- Registration: `pi.registerProvider("opencode", { baseUrl, apiKey, api: "opencode" as Api,
  streamSimple: makeZenStreamer(streamSimple), models })` — **custom api name** because omp
  reserves built-in api names for its own handlers; the real per-model `api` is restored
  inside `makeZenStreamer`. No `refreshModels` — the registry is read once per plugin
  load (omp exposes no host refresh protocol for extensions); `session_start` only
  rotates the session id.
- Same early-return on empty list; `session_start` → `rotateSession`.

### 5.5 Behavioral contract summary (from README + commits)

- Only **free, non-deprecated** opencode models surface; single provider id `opencode`
  (no `opencode-patched`); pi.dev registry is the authoritative catalog source for both
  hosts (with the per-host fallbacks in §4.3); freshness gate mirrors the host
  `withRemoteCatalog`; boot must work offline; `npm test` runs under node **and** bun.
- Verified 2026-09-25: `pi --list-models` (the real subcommand — bare `pi models` starts a
  session and hangs) → exactly the ground-truth 8 under `opencode`; `omp models` →
  `opencode (8)`; typecheck + node/bun smoke green; live conversation PONG for local
  `pi -p` / `omp -p` / `opencode run` / `reasonix -p` and paseo `omp` / `dsh` /
  `opencode2` / `maki`.

---

## 6. Compatibility risks

1. **OMP requires Bun ≥ 1.3.14** (`engines.bun`); Node cannot run the `omp` CLI. CI adds
   `nixpkgs#bun` deliberately (the `omp` shebang and smoke test need it — `9177e3f3`).
2. **dsh engine window** `^22.19.0 || >=24` — this environment's Node v22.23.2 satisfies it.
   The 2026-09-24 session briefly had a broken global install
   (`@deepseek-ai/dsh-subprocess-local/lib/runner.js` missing) which broke that session's
   shell; a clean `deepseekharness-acp-interactive@1.3.2` install was verified working
   on 2026-09-25 (zen conversation PONG end-to-end).
3. **Two opencode lines / UA pin drift:** docs install `opencode-ai@1.18.32` while the repo
   installs `@opencode/cli@2.0.16`; wire pins are anchored to `opencode/1.18.32`, and the
   local `generate-settings.py` sends `opencode/2.0.16`. **Gateway acceptance of the v2 UA
   is now VERIFIED (2026-09-25):** with the headers patch applied, dsh's `opencode/2.0.16 …`
   identity passes the Zen gate end-to-end (conversation PONG); without the patch (UA
   `deepseek-harness/...`) the same request gets `403 FreeTierError` — the A/B is
   documented in `.github/dsh/README.md`.
4. **Pin alignment (origin main at research time):** origin still had
   `deepseekharness-acp-interactive@1.3.0`, `reasonix@1.38.12`, `@oh-my-pi/pi-coding-agent@18.2.6`.
   The working tree now pins `@getpaseo/cli@0.9.2`, pi `0.87.1`, omp `18.3.0`,
   dsh `1.3.2`, reasonix `1.39.0`, `@opencode/cli@2.0.16`, and `pi-opencode` deps
   aligned to `@oh-my-pi/*@18.3.0`.
5. **Conversation smoke:** existed in `1334d0da`/`071e06fd`, was deleted by `d5c297c3`,
   and is **restored in the working tree** (local 4 + paseo 4 PONG matrix), plus dynamic
   model-list assertions via a shared `assert_model_list` helper (space-bunny present,
   the three retired ids absent across `pi --list-models`, `omp models`, dsh settings,
   reasonix config, and `paseo provider models dsh/omp/maki/opencode2`). The assertions
   are written as `if …; then exit 1` — a bare `! cmd` under `set -e` returns 1 without
   aborting the script, which silently no-ops the assertion (verified by reproduction).
6. **Gateway liveness semantics are subtle:** 403 FreeTier ≠ dead; only
   `400 "Model is unavailable"` means dead. Fail-open vs fail-closed on network errors
   differs between origin (open) and local (closed) `generate-settings.py`.
7. **ACP defaults:** dsh ACP default route is `deepseek-official`; paseo must pass
   `--model zen:<id>`. Provider entries are inert until `paseo reload` after editing
   `~/.paseo/config.json`; provider ids must match `/^[a-z][a-z0-9-]*$/`.
8. **`@opencode/cli` is a binary wrapper** (postinstall + per-platform optional deps);
   restricted/air-gapped installs may need the platform package explicitly.
9. **pi legacy Node line:** `legacy-node20` = 0.74.2 for Node < 22.19; the current line
   needs Node ≥ 22.19.0.
10. **reasonix maintenance status:** upstream README calls the TS line legacy and points at a
    Go rewrite (`main-v2`); pin deliberately and check the branch provenance of `1.39.0`
    before relying on new features (**UNVERIFIED**).
11. **Local working tree ≠ origin** for at least two files (§2.3); a full diff must be run
    from a working shell before any commit.

## 7. Explicitly UNVERIFIED

- Whether npm `reasonix@1.39.0` is built from the `main-v2` (Go) or legacy TS branch.
- Whether a maki auto-compaction CI step exists anywhere besides the `d5c297c3` message.
- Whether GitHub `main` advanced after 2026-09-24T22:05:49Z (feeds may be CDN-cached).

Resolved since the research date (2026-09-25):

- ~~Zen gateway acceptance of `opencode/2.0.16` UA~~ — verified working (A/B, see §6.3).
- ~~Full local-vs-origin diff~~ — `git status/diff` runs normally from the working shell.
- ~~CLI `--help` outputs~~ — verified locally for `paseo` (and per-package smoke for
  `pi`/`omp`/`opencode`/`reasonix`).

---

## 8. Verification addendum (2026-09-25, empirical)

### 8.1 Ground-truth free model list

pi.dev registry (`/api/models/providers/opencode`, `free` entries) and models.dev
(`provider.opencode`, `cost == 0` and `status != "deprecated"`) agree **exactly** on 8 ids:

`big-pickle`, `ling-3.0-flash-fin-free`, `mimo-v2.6-flash-free`,
`muse-spark-1.2-contributor-free`, `muse-spark-1.3-contributor-free`,
`nemotron-3-ultra-free`, `nemotron-3.5-lightning-free`, `space-bunny-free`.

The gateway `GET /models` (80 ids) additionally lists 3 ids that are **not** in this
set and must never surface: `deepseek-v4-flash-free` (400 dead + models.dev deprecated),
`mimo-v2.5-free` (models.dev deprecated), `jev-1.13-free` (absent from models.dev) —
`gateByLive()` now enforces them as a permanent retired set (§4.3). Completions-capable
subset = the 8 minus the two `openai-responses` muse-spark models → **6** (all 6 pass for
patched dsh); reasonix reaches that same 6 but its client profile is gated, so only
`space-bunny-free` passes there (§8.2) → its vendored list is **1**.

### 8.2 Zen gate matrix (observed)

| model / client | result |
|---|---|
| `mimo-v2.6-flash-free`, `mimo-v2.5-free` via curl | `403 FreeTierError` (client-profile gate) |
| `big-pickle`, `ling-3.0-flash-fin-free`, `mimo-v2.6-flash-free`, `nemotron-3-ultra-free`, `nemotron-3.5-lightning-free` via reasonix (`-p --model …`) | `403` — all five verified 2026-09-25 (reasonix reports it as an auth failure) |
| `space-bunny-free` via reasonix (default model) | `200`, conversation PONG — the only zen model reasonix can use |
| `mimo-v2.6-flash-free` via opencode-native clients / patched dsh | `200`, conversation PONG |
| `space-bunny-free` via any client | `200`, open |
| `deepseek-v4-flash-free` | `400 Model is unavailable` (dead) |

Provider-level header overrides in reasonix (`headers = { … }` on the provider block) do
**not** change the outcome — UA-only and the full five-header set were both tried and still
403, so reasonix cannot adopt the opencode identity; only the open model works.

### 8.3 Final per-host lists (verified this session)

| surface | source | count / content |
|---|---|---|
| local `pi --list-models` | builtin ∪ pi.dev boot (store only when the boot fetch fails) | `opencode` rows = exactly the 8 (plus pi's builtin nvidia rows) |
| local `omp models` | pi.dev registry | `opencode (8)` |
| `paseo provider models omp` | pi.dev registry + omp's other bundled providers | 178 data rows; `opencode/*` = the 8 |
| `paseo provider models maki` | models.dev free + non-deprecated (opencode + nvidia) | 26 data rows; opencode free = the 8 |
| `paseo provider models opencode2` | opencode runtime catalog (models.dev, incl. paid) | 179 data rows; `opencode/*` = 76; zen free = the 8 |
| `paseo provider models dsh` | `~/.dsh/settings.yaml` + dsh's own built-ins | 9 data rows; `zen:` = 6 (plus 3 `deepseek-official:*` built-ins) |
| `~/.dsh/settings.yaml` | generator (gateway ∩ models.dev + status + liveness) | 6 |
| `~/.reasonix/config.toml` | vendored, gate-limited | 1 — `space-bunny-free` only (the other five completions ids 403 this client, §8.2) |

On every one of these surfaces (2026-09-25): `space-bunny-free` present, the three retired
ids absent — asserted in `paseo.yml`.

### 8.4 Paseo provider model snapshots need an explicit refresh

`paseo reload` re-reads `config.json` but does **not** refresh
`provider-snapshot-manager`'s in-memory model snapshots — `paseo provider models <id>`
kept serving the session-start list (stale `mimo-v2.5-free`/`deepseek-v4-flash-free`)
until the snapshot was refreshed. The daemon exposes this without a restart via the
websocket `refresh_providers_snapshot_request` (the same call the web-UI refresh button
sends; handler in
`@getpaseo/server …/session/provider/provider-catalog-session.js` →
`refreshSettingsSnapshot`). An ad-hoc daemon-client snippet (run from `/tmp`, built on
`connectToDaemon` + `refreshProvidersSnapshot({})` — not vendored in this repo)
acknowledged the refresh, and the very next `paseo provider models dsh`/`omp` returned the
correct 6/8 lists.
A fresh daemon (every CI run) snapshots after the install step, so no refresh is needed
there; the workflow now also asserts the lists.

## 9. Source list (full URLs)

Registry:
- https://registry.npmjs.org/reasonix/latest , /reasonix/1.39.0
- https://registry.npmjs.org/@getpaseo%2Fcli/latest , https://registry.npmjs.org/-/package/@getpaseo%2Fcli/dist-tags
- https://registry.npmjs.org/@earendil-works%2Fpi-coding-agent/latest
- https://registry.npmjs.org/@oh-my-pi%2Fpi-coding-agent/latest
- https://registry.npmjs.org/deepseekharness-acp-interactive/latest
- https://registry.npmjs.org/@opencode%2Fcli/latest
- https://registry.npmjs.org/opencode-ai/latest

Paseo:
- https://paseo.sh/docs.md , https://paseo.sh/docs/cli.md , https://paseo.sh/docs/custom-providers.md
- https://paseo.sh/docs/providers.md , https://paseo.sh/docs/supported-providers.md
- https://paseo.sh/docs/troubleshooting.md , https://paseo.sh/llms.txt

OpenCode:
- https://opencode.ai/docs/ , https://opencode.ai/docs/models/ , https://opencode.ai/docs/providers/
- https://opencode.ai/docs/zen/ , https://opencode.ai/docs/cli/ , https://opencode.ai/install
- https://github.com/anomalyco/opencode

pi / omp / dsh / reasonix:
- https://pi.dev/docs/latest , https://pi.dev/docs/latest/quickstart
- https://raw.githubusercontent.com/earendil-works/pi/main/README.md
- https://omp.sh , https://raw.githubusercontent.com/can1357/oh-my-pi/main/README.md
- https://raw.githubusercontent.com/ClickPM/dsh-acp-interactive/main/README.md
- https://raw.githubusercontent.com/esengine/reasonix/main/README.md
- https://esengine.github.io/DeepSeek-Reasonix/configuration.html

kyehn/kudzu:
- https://github.com/kyehn/kudzu/commits/main.atom
- https://github.com/kyehn/kudzu/commits/main/.github/pi-opencode.atom
- https://github.com/kyehn/kudzu/commits/main/.github/workflows/paseo.yml.atom
- https://github.com/kyehn/kudzu/commits/main/.github/paseo-config.json.atom
- https://github.com/kyehn/kudzu/commits/main/.github/dsh/generate-settings.py.atom
- https://github.com/kyehn/kudzu/commits/main/overlays/maki/providers-config.py.atom
- https://github.com/kyehn/kudzu/commit/1334d0dad60d9c7473abd8e07ce0c8a3c7ccb3a7.patch
- https://github.com/kyehn/kudzu/commit/071e06fd9784fba56d7e4fc9f98355fd77bf643d.patch
- https://github.com/kyehn/kudzu/commit/d5c297c35598f74d9bfbd2ec4566a5c516606276.patch
- https://github.com/kyehn/kudzu/commit/91787e35634a0a50ddd8f15fac306f77d023b4 (feed entry)
- https://raw.githubusercontent.com/kyehn/kudzu/d5c297c35598f74d9bfbd2ec4566a5c516606276/.github/workflows/paseo.yml
- https://raw.githubusercontent.com/kyehn/kudzu/d5c297c35598f74d9bfbd2ec4566a5c516606276/.github/dsh/generate-settings.py
- https://cdn.jsdelivr.net/gh/kyehn/kudzu@main/ (tree API: https://data.jsdelivr.com/v1/packages/gh/kyehn/kudzu@main)
- Local reads: `.github/pi-opencode/{package.json,shared.ts,pi.ts,omp.ts}`,
  `.github/dsh/generate-settings.py`, `.github/workflows/paseo.yml`, `overlays/maki/README.md`
