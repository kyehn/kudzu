#!/usr/bin/env nix-shell
#!nix-shell -i bash -p bash nixVersions.latest go-task

export NIX_CONFIG="experimental-features = nix-command flakes cgroups"

task install
# NIX_PATH="nixpkgs=/nix/store" task install
