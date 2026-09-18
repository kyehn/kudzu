# Declarative maki policy counterpart of overlays/maki/maki-config.py.
#
# Boundary (hard rule): this file renders NO providers.toml. Provider and
# model data (slugs, base URLs, keys, headers, per-wire User-Agents,
# declared [[models]] snapshots) are live data and are generated ONLY by
# overlays/maki/maki-config.py. Nix stays declarative policy-only, so the
# free catalog can drift without editing nix.
#
# What this file does render, via the nix-provided Lua function: init.lua.
# maki only honors init.lua through the maki.setup() call, so the
# nix-provided Lua serializer covers the argument and writeText adds the
# call wrapper. Signature per https://noogle.dev/f/lib/generators/toLua/:
# toLua :: { multiline; indent; asBindings; } -> Any -> String
# (empty options select the multiline default).
#
# Attribute mapping from overlays/reasonix-config.nix (only what maki's
# init.lua honors is rendered here):
# - default_model -> provider.default_model, pointing at the py-managed
#   zen-responses custom slug (refresh the id from maki-config.py output
#   when the free catalog drifts).
# - allowed provider set -> provider.allowed_models (the three py-managed
#   custom slugs; `*` matches `/`, so `zen-chat/*` covers nested ids).
# - config_version/language/ui/agent/tools/lsp/skills/permissions/sandbox/
#   bot/secrets/plugins have no init.lua equivalent (maki keeps behavior
#   in permissions.toml, mcp.toml and the py-generated provider tables)
#   -> intentionally absent here.
{
  lib,
  writeText,
}:

# formats.lua renders a bare table, but maki only honors init.lua through
# the maki.setup() call, so the nix-provided Lua serializer covers the
# argument and writeText adds the call wrapper. Renders:
# maki.setup({ ["provider"] = { ["default_model"] = ...; ... } }).
writeText "init.lua" ''
  maki.setup(${
    lib.generators.toLua { } {
      provider = {
        default_model = "zen-responses/muse-spark-1.3-contributor-free";
        allowed_models = [
          "zen-chat/*"
          "zen-responses/*"
          "nvidia/*"
        ];
      };
    }
  })
''
