#!/usr/bin/env bash
# gate-godot-headless: import the fixture Godot project, run the nmg_game_dev add-on tests, and
# check the asset probe against the fixture Crate.glb.
#
#   scripts/run-godot-tests.sh
#
# Godot resolution (never pinned):
#   1. GODOT_BIN, which must be executable.
#   2. godot on PATH.
#   3. The latest stable release from GitHub (the tag of
#      https://api.github.com/repos/godotengine/godot/releases/latest), unpacked into
#      .cache/godot/<tag>/ (git-ignored; GODOT_CACHE_DIR overrides the .cache/godot folder) and
#      reused on later runs. Without network access the newest cached copy is used.
#
# Steps, in a mktemp -d copy of tests/godot/fixture/ with the add-on installed at
# addons/nmg_game_dev:
#   1. godot --headless --import must exit 0 and print no ERROR: line.
#   2. res://addons/nmg_game_dev/tests/run_tests.gd must exit 0, print "N passed, 0 failed", and
#      print no ERROR: or SCRIPT ERROR: line.
#   3. src/nmg_game_dev/godot/gd/probe_asset.gd on res://Crate.glb must print an NMG_RESULT line
#      that matches tests/godot/fixture/expected-probe.json (floats within 0.001).
#
# Exit codes:
#   0  every step passed
#   2  GODOT_BIN is set but is not an executable file
#   3  Godot could not be downloaded (no network, no matching release asset, unsupported OS)
#   4  the fixture import failed
#   5  the add-on tests failed
#   6  the probe failed or printed no NMG_RESULT line
#   7  the probe result differs from expected-probe.json
# Each failure prints ERROR: and Remediation: lines on stderr.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture="$repo_root/tests/godot/fixture"
addon="$repo_root/plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev"
probe="$repo_root/src/nmg_game_dev/godot/gd/probe_asset.gd"
cache_root="${GODOT_CACHE_DIR:-$repo_root/.cache/godot}"
latest_url="https://api.github.com/repos/godotengine/godot/releases/latest"

die() {
  local code="$1" remediation="$2" message="$3"
  printf 'ERROR: %s\n' "$message" >&2
  printf 'Remediation: %s\n' "$remediation" >&2
  exit "$code"
}

cached_binary() {
  local dir="$1"
  case "$(uname -s)" in
    Darwin) printf '%s\n' "$dir/Godot.app/Contents/MacOS/Godot" ;;
    *) printf '%s\n' "$dir/Godot_v$(basename "$dir")_linux.x86_64" ;;
  esac
}

newest_cached() {
  local dir newest=""
  [[ -d "$cache_root" ]] || return 1
  while IFS= read -r dir; do
    [[ -x "$(cached_binary "$cache_root/$dir")" ]] && newest="$dir"
  done < <(find "$cache_root" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort -V)
  [[ -n "$newest" ]] || return 1
  cached_binary "$cache_root/$newest"
}

download_godot() {
  local tag asset dest zip binary
  if ! tag="$(curl -fsSL "$latest_url" | python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])')" || [[ -z "$tag" ]]; then
    if binary="$(newest_cached)"; then
      printf 'WARNING: could not query the latest Godot release; using %s\n' "$binary" >&2
      printf '%s\n' "$binary"
      return 0
    fi
    die 3 "Install Godot 4 or set GODOT_BIN, or rerun with network access to GitHub." "could not query the latest Godot release from $latest_url"
  fi
  case "$(uname -s)" in
    Darwin) asset="Godot_v${tag}_macos.universal.zip" ;;
    Linux) asset="Godot_v${tag}_linux.x86_64.zip" ;;
    *) die 3 "Install Godot 4 and set GODOT_BIN to its executable." "no Godot download for $(uname -s)" ;;
  esac
  dest="$cache_root/$tag"
  binary="$(cached_binary "$dest")"
  if [[ -x "$binary" ]]; then
    printf '%s\n' "$binary"
    return 0
  fi
  mkdir -p "$dest"
  zip="$dest/$asset"
  printf 'Downloading %s into %s\n' "$asset" "$dest" >&2
  curl -fsSL -o "$zip" "https://github.com/godotengine/godot/releases/download/${tag}/${asset}" \
    || die 3 "Check network access to GitHub, or install Godot 4 and set GODOT_BIN." "could not download $asset"
  unzip -q -o "$zip" -d "$dest" \
    || die 3 "Delete $dest and rerun, or install Godot 4 and set GODOT_BIN." "could not unpack $asset"
  rm -f "$zip"
  [[ -x "$binary" ]] || die 3 "Delete $dest and rerun, or install Godot 4 and set GODOT_BIN." "the download did not contain $binary"
  printf '%s\n' "$binary"
}

resolve_godot() {
  if [[ -n "${GODOT_BIN:-}" ]]; then
    [[ -f "$GODOT_BIN" && -x "$GODOT_BIN" ]] \
      || die 2 "Point GODOT_BIN at the Godot 4 executable, or unset it to use godot on PATH." "GODOT_BIN is not an executable file: $GODOT_BIN"
    printf '%s\n' "$GODOT_BIN"
    return 0
  fi
  if command -v godot >/dev/null 2>&1; then
    command -v godot
    return 0
  fi
  download_godot
}

godot="$(resolve_godot)"
printf 'Godot: %s\n' "$godot"

project="$(mktemp -d)"
cleanup() {
  rm -rf "$project"
}
trap cleanup EXIT

cp -R "$fixture/." "$project/"
mkdir -p "$project/addons"
cp -R "$addon" "$project/addons/nmg_game_dev"

run_godot() {
  "$godot" --headless --audio-driver Dummy --path "$project" "$@" 2>&1
}

# 1. Import the fixture project.
status=0
output="$(run_godot --import)" || status=$?
printf '%s\n' "$output"
if (( status != 0 )) || grep -q '^ERROR:' <<<"$output"; then
  first="$(grep -m 1 '^ERROR:' <<<"$output" || true)"
  die 4 "Read the import output above and fix the fixture or the add-on, then rerun." "fixture import failed (exit $status) ${first}"
fi

# 2. Run the add-on tests.
status=0
output="$(run_godot -s res://addons/nmg_game_dev/tests/run_tests.gd)" || status=$?
printf '%s\n' "$output"
if (( status != 0 )) \
  || grep -qE '^(SCRIPT )?ERROR:' <<<"$output" \
  || ! grep -qE '^[0-9]+ passed, 0 failed$' <<<"$output"; then
  die 5 "Fix the failing add-on test or script error reported above, then rerun." "add-on tests failed (exit $status)"
fi

# 3. Probe the fixture Crate.glb and compare with the expected result.
probe_dir="$project/.godot/nmg_probes"
mkdir -p "$probe_dir"
cp "$probe" "$probe_dir/probe_asset.gd"
params="$probe_dir/probe_asset.params.json"
printf '{"glb": "res://Crate.glb"}\n' >"$params"
status=0
output="$(run_godot -s res://.godot/nmg_probes/probe_asset.gd -- "$params")" || status=$?
printf '%s\n' "$output"
result="$(grep '^NMG_RESULT ' <<<"$output" | tail -n 1 || true)"
if (( status != 0 )) || [[ -z "$result" ]]; then
  die 6 "Read the probe output above; check that the fixture imported and probe_asset.gd parses." "probe_asset.gd failed (exit $status) or printed no NMG_RESULT line"
fi

if ! python3 - "${result#NMG_RESULT }" "$fixture/expected-probe.json" <<'PY'
import json
import sys

TOLERANCE = 0.001


def diff(actual, expected, where):
    if isinstance(expected, bool) or isinstance(actual, bool):
        return [] if actual == expected else [f"{where}: {actual!r} != {expected!r}"]
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if abs(actual - expected) <= TOLERANCE:
            return []
        return [f"{where}: {actual!r} != {expected!r}"]
    if isinstance(expected, dict) and isinstance(actual, dict):
        if sorted(actual) != sorted(expected):
            return [f"{where}: keys {sorted(actual)} != {sorted(expected)}"]
        return [line for key in expected for line in diff(actual[key], expected[key], f"{where}.{key}")]
    if isinstance(expected, list) and isinstance(actual, list):
        if len(actual) != len(expected):
            return [f"{where}: {len(actual)} items != {len(expected)}"]
        return [line for i, (a, e) in enumerate(zip(actual, expected)) for line in diff(a, e, f"{where}[{i}]")]
    return [] if actual == expected else [f"{where}: {actual!r} != {expected!r}"]


try:
    actual = json.loads(sys.argv[1])
except ValueError as error:
    print(f"probe result is not JSON: {error}", file=sys.stderr)
    raise SystemExit(1)
with open(sys.argv[2], encoding="utf-8") as handle:
    expected = json.load(handle)
problems = diff(actual, expected, "result")
for problem in problems:
    print(problem, file=sys.stderr)
raise SystemExit(1 if problems else 0)
PY
then
  die 7 "Fix the probe or the importer, or regenerate the fixture with tests/godot/make_crate_glb.py and update expected-probe.json." "the probe result differs from tests/godot/fixture/expected-probe.json"
fi

echo "gate-godot-headless: import, add-on tests, and probe passed"
