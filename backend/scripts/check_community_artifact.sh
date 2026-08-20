#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$script_dir/.."

artifact_dir=$(mktemp -d)
uv build --out-dir "$artifact_dir" >/dev/null
wheel_path=$(find "$artifact_dir" -maxdepth 1 -type f -name '*.whl' -print -quit)

if [[ -z "$wheel_path" ]]; then
  echo "Community artifact check failed: wheel was not built" >&2
  exit 1
fi

if unzip -l "$wheel_path" | grep -Eiq '(^|/)(pro|private)(/|\.)'; then
  echo "Community artifact check failed: Pro/private path found in wheel" >&2
  exit 1
fi

echo "Community artifact check passed: $(basename "$wheel_path")"
