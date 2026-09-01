#!/usr/bin/env bash
# PostToolUse hook: format the file Claude just edited.
#
# Silently does nothing when the formatter is not installed yet, so a fresh
# clone never fails on every edit. Never blocks: always exits 0.

set -uo pipefail

project_dir="${CLAUDE_PROJECT_DIR:-$(pwd)}"

command -v bun >/dev/null 2>&1 || exit 0

file_path="$(
  bun -e 'const raw = await Bun.stdin.text();
          try { process.stdout.write(JSON.parse(raw)?.tool_input?.file_path ?? ""); }
          catch { process.stdout.write(""); }' 2>/dev/null
)"

[[ -n "$file_path" && -f "$file_path" ]] || exit 0

case "$file_path" in
  *.ts | *.tsx | *.js | *.json)
    if [[ -x "$project_dir/node_modules/.bin/biome" ]]; then
      "$project_dir/node_modules/.bin/biome" format --write "$file_path" >/dev/null 2>&1
    fi
    ;;
  *.py)
    if command -v uv >/dev/null 2>&1 && [[ -d "$project_dir/worker/.venv" ]]; then
      (cd "$project_dir/worker" && uv run ruff format "$file_path") >/dev/null 2>&1
    fi
    ;;
esac

exit 0
