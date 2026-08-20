#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/.." && pwd)
source_dir=${1:-}
mode=${2:---preflight}

if [[ -z "$source_dir" || ! -d "$source_dir" ]]; then
  echo "Usage: $0 COMMUNITY_DIRECTORY [--preflight|--release]" >&2
  exit 2
fi
source_dir=$(realpath -- "$source_dir")

fail() { echo "Community release check failed: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

for required in LICENSE NOTICE README.md SECURITY.md CONTRIBUTING.md CHANGELOG.md backend/pyproject.toml web/package-lock.json compose.demo.yaml; do
  [[ -f "$source_dir/$required" ]] || fail "missing $required"
done
pass "required public files"

if find "$source_dir" -type f \( -path '*/docs/adr/*' -o -path '*/docs/open-core/*' -o -name 'development_progress.md' -o -name '*acceptance.md' -o -name '.env' \) -print -quit | grep -q .; then
  fail "internal-only file found"
fi
pass "internal-only paths excluded"

if rg -n --hidden --glob '!**/.venv/**' --glob '!**/node_modules/**' --glob '!LICENSE' --glob '!web/package-lock.json' --glob '!backend/uv.lock' --glob '!**/scripts/check-community-release.sh' \
  '(/home/[^/[:space:]]+|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3})' "$source_dir"; then
  fail "private path or concrete private-network address found"
fi
pass "private path/address scan"

if rg -n --hidden --glob '!**/.venv/**' --glob '!**/node_modules/**' --glob '!**/scripts/check-community-release.sh' \
  '(-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,})' "$source_dir"; then
  fail "possible embedded secret found"
fi
pass "basic secret scan"

if rg -n --hidden --glob '!**/.venv/**' --glob '!**/node_modules/**' --glob '!**/scripts/check-community-release.sh' '(docs/(open-core|adr)/|development_progress\.md|frigate_ai_research|北美安防)' "$source_dir"; then
  fail "public file links to internal documentation"
fi
pass "internal link scan"

"$source_dir/backend/scripts/check_community_artifact.sh"
pass "Python wheel boundary"

if command -v syft >/dev/null 2>&1; then
  community_version=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$source_dir/backend/pyproject.toml" | head -n 1)
  [[ -n "$community_version" ]] || fail "unable to read Community version from backend/pyproject.toml"
  mkdir -p "$source_dir/release"
  syft dir:"$source_dir" \
    --source-name nanexus-event-intelligence \
    --source-version "$community_version" \
    --exclude './release/**' \
    -o spdx-json="$source_dir/release/sbom.spdx.json" >/dev/null
  pass "SPDX SBOM generated"
elif [[ "$mode" == "--release" ]]; then
  fail "syft is required in release mode to generate SPDX SBOM"
else
  echo "WARN: syft unavailable; release mode will require an SPDX SBOM"
fi

if [[ "$mode" != "--preflight" && "$mode" != "--release" ]]; then
  fail "unknown mode: $mode"
fi

pass "Community release $mode checks"
