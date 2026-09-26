{
  lib,
  formats,
  linkFarm,
  writeText,
  opencode-wire,
  mcp-nixos,
  context7-mcp,
  codegraph,
  open-websearch,
}:
let
  yaml = formats.yaml { };
  profileName = "default";
  cordisPatch = yaml.generate "cordis.patch.yml" [
    {
      id = "sandbox-policy";
      config.mode = "workspace-write";
    }
    {
      id = "approval";
      config.policy = "ask";
    }
    {
      id = "agent-default-model";
      config = {
        provider = "opencode-openai";
        model = "space-bunny-free";
      };
    }
    {
      # dsh-acp-enhanced's own row reads
      # `!!js process.env.DSH_ACP_PROVIDER ?? 'deepseek-official'`; leaving it
      # unset routes every turn at a provider that is not mounted, so the same
      # route is pinned here — one id, no second source of truth, no env var.
      id = "acp-enhanced";
      config = {
        provider = "opencode-openai";
        model = "space-bunny-free";
      };
    }
    {
      # maki task.max_concurrent=3: the harness knob is the tool fan-out.
      id = "agent-loop";
      config.maxParallelToolCalls = 3;
    }
    {
      # pi quietStartup / enableSkillCommands=false: instructions are still
      # discovered (the agent needs them) with an explicit byte budget.
      id = "agent-instructions";
      config.maxBytes = 65536;
    }
    {
      # pi permission.path (*.env deny, *.env.example allow) has no path-filter
      # field in dsh; the closest real knobs are the search caps, and an
      # over-cap glob never samples a match (so no .env can ride along).
      id = "tool-fs-search";
      config = {
        sampleOverCapGlobResults = false;
        globMaxResults = 100;
        grepMaxMatches = 250;
      };
    }
    {
      # Read caps, so one runaway read cannot eat the context window.
      id = "tool-fs";
      config = {
        readLimit = 2000;
        readMaxLineLength = 2000;
        readMaxBytes = 262144;
      };
    }
    {
      # Each call is a fresh shell, so there is no background job to promote.
      id = "tool-bash";
      config = {
        enableRunInBackground = false;
        promoteOnTimeout = false;
      };
    }
    {
      # DeepSeek-only rows. No DEEPSEEK_API_KEY exists here, so the official
      # model route and its web search/fetch provider must not mount.
      id = "llm-deepseek";
      disabled = true;
    }
    {
      id = "llm-deepseek-account";
      disabled = true;
    }
    {
      id = "web-search-deepseek";
      disabled = true;
    }
    {
      id = "web-fetch-http";
      disabled = true;
    }
    {
      id = "mcp-nixos";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "nixos";
        transport = "stdio";
        command = lib.getExe mcp-nixos;
      };
    }
    {
      id = "mcp-context7";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "context7";
        transport = "stdio";
        command = lib.getExe context7-mcp;
      };
    }
    {
      id = "mcp-mobile";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "mobile";
        transport = "stdio";
        command = "mcp-server-mobile";
      };
    }
    {
      id = "mcp-codegraph";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "codegraph";
        transport = "stdio";
        command = lib.getExe codegraph;
        args = [
          "serve"
          "--mcp"
        ];
      };
    }
    {
      id = "mcp-websearch";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "websearch";
        transport = "stdio";
        command = lib.getExe open-websearch;
        env = {
          SEARCH_MODE = "request";
          DEFAULT_SEARCH_ENGINE = "duckduckgo";
          MODE = "stdio";
        };
      };
    }
    {
      id = "mcp-grepapp";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "grepapp";
        transport = "streamable-http";
        url = "https://mcp.grep.app";
      };
    }
  ];

  profilePackage = writeText "package.json" (
    builtins.toJSON {
      name = "dsh-profile-${profileName}";
      private = true;
      # billion-context-dsh is deliberately NOT listed. Every published version
      # (0.2.x and 0.3.0) declares peerDependencies on dsh >=0.1.5-alpha.1
      # <0.1.6-0, which excludes 0.1.7-rc.2. The version gate can be waived
      # (`dsh plugin allow-version`) and the bundle does mount its
      # `compaction-acp` row, but every conversation then dies inside its
      # compaction backend with `turn failed: Cannot read properties of
      # undefined (reading 'some')` (verified on 0.3.0, waiver active).
      # `compaction-basic` from dsh-base is the working equivalent meanwhile.
      dsh.profile.bundles = [
        "@deepseek-ai/dsh-base"
        "dsh-acp-enhanced"
        "opencode-wire"
      ];
      # opencode-wire is intentionally NOT a file: dependency here: pnpm cannot
      # hardlink a nix-store path (read-only) into a mutable profile closure
      # (`Operation not permitted`), so it is packed (`pnpm pack`) and mounted
      # with `dsh plugin add <tarball>` after the registry bundles install.
      dependencies = {
        "@deepseek-ai/dsh-base" = "0.1.7-rc.2";
        dsh-acp-enhanced = "0.9.1";
      };
    }
  );
in
linkFarm "dsh-config" [
  {
    name = "cordis.patch.yml";
    path = cordisPatch;
  }
  {
    name = "package.json";
    path = profilePackage;
  }
]
