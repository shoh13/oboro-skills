#!/usr/bin/env bash
# Usage: check-plugin-version.sh <base-ref> [<head-ref>]
# Fails when the two plugin manifests disagree on the version, or when the plugin
# changed since <base-ref> and the version is not greater than the one at <base-ref>.
set -euo pipefail
base=$1 head=${2:-HEAD}
manifests=(oboro/.claude-plugin/plugin.json oboro/.codex-plugin/plugin.json)

version_at() { git show "$1:$2" | jq -er .version; }

head_version=$(version_at "$head" "${manifests[0]}")
for m in "${manifests[@]:1}"; do
  v=$(version_at "$head" "$m")
  if [ "$v" != "$head_version" ]; then
    echo "::error file=$m::version $v differs from ${manifests[0]} ($head_version)"
    exit 1
  fi
done

changed=$(git diff --name-only "$base" "$head" -- oboro .claude-plugin .agents/plugins)
if [ -z "$changed" ]; then
  echo "plugin unchanged; version $head_version"
  exit 0
fi

base_version=$(version_at "$base" "${manifests[0]}")
highest=$(printf '%s\n%s\n' "$base_version" "$head_version" | sort -V | tail -n1)
if [ "$head_version" = "$base_version" ] || [ "$highest" != "$head_version" ]; then
  echo "::error file=${manifests[0]}::plugin changed but version $head_version is not greater than $base_version on the base branch. Bump it in: ${manifests[*]}"
  echo "changed files:"; echo "$changed"
  exit 1
fi
echo "version $base_version -> $head_version"
