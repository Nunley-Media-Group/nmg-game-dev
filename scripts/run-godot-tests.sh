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
#      https://api.github.com/repos/godotengine/godot/releases/latest, which must look like
#      4.x-stable), checked against the release's SHA512-SUMS.txt, unpacked into
#      .cache/godot/<tag>/ (git-ignored; GODOT_CACHE_DIR overrides the .cache/godot folder) and
#      reused on later runs. Without network access the newest cached copy is used.
#
# Steps, in a mktemp -d copy of tests/godot/fixture/ with the add-on installed at
# addons/nmg_game_dev and a generated 0.1 s mono WAV at res://Beep.wav:
#   1. godot --headless --import must exit 0 and print no ERROR: line.
#   2. res://addons/nmg_game_dev/tests/run_tests.gd must exit 0, print "N passed, 0 failed", print
#      no ERROR: or SCRIPT ERROR: line, and print a PASS line for each test in required_tests (the
#      variant-routing tests, and the NmgLaunch option, autoplay, and save-folder tests).
#   3. src/nmg_game_dev/godot/gd/probe_asset.gd on res://Crate.glb must print an NMG_RESULT line
#      that matches tests/godot/fixture/expected-probe.json (floats within 0.001).
#   4. Every src/nmg_game_dev/godot/gd/*.gd must pass godot --check-only.
#   5. probe_anims.gd on the fixture rig and its three animation_library clips, and
#      probe_terrain.gd in scene mode on the fixture terrain, must print the NMG_RESULT in
#      tests/godot/fixture/expected-anims.json and expected-terrain.json (floats within 0.001;
#      tests/godot/make_probe_fixtures.py writes those fixtures). probe_terrain.gd in meshes mode
#      (Crate.glb) and probe_audio.gd (res://Beep.wav) must print the NMG_RESULT shape the Python
#      side reads.
#
# Every Godot run is bounded by GODOT_GATE_TIMEOUT seconds (default 300), so a Godot that stalls
# fails the gate instead of hanging it.
#
# Exit codes:
#   0  every step passed
#   2  GODOT_BIN is set but is not an executable file
#   3  Godot could not be downloaded (no network, no matching release asset, unsupported OS)
#   4  the fixture import failed
#   5  the add-on tests failed
#   6  the probe failed or printed no NMG_RESULT line
#   7  the probe result differs from expected-probe.json
#   8  a probe script failed --check-only
#   9  a probe smoke run failed, printed the wrong result shape, or differs from its expected file
#   10 a Godot run exceeded GODOT_GATE_TIMEOUT
# Each failure prints ERROR: and Remediation: lines on stderr.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture="$repo_root/tests/godot/fixture"
addon="$repo_root/plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev"
probes="$repo_root/src/nmg_game_dev/godot/gd"
probe="$probes/probe_asset.gd"
gate_timeout="${GODOT_GATE_TIMEOUT:-300}"
required_tests=(
  "test_nmg_assets.gd::test_desktop_variant"
  "test_nmg_assets.gd::test_mobile_variant"
  "test_nmg_assets.gd::test_malformed_path_is_unchanged_with_a_warning"
  "test_nmg_launch.gd::test_cmdline_options"
  "test_nmg_launch.gd::test_web_hash_options"
  "test_nmg_launch.gd::test_flag_reads_true"
  "test_nmg_launch.gd::test_absent_option_returns_default"
  "test_nmg_launch.gd::test_autoplay_emits_once"
  "test_nmg_launch.gd::test_save_dir_with_test_saves"
  "test_nmg_launch.gd::test_save_dir_default"
)
cache_root="${GODOT_CACHE_DIR:-$repo_root/.cache/godot}"
latest_url="https://api.github.com/repos/godotengine/godot/releases/latest"

die() {
  local code="$1" remediation="$2" message="$3"
  printf 'ERROR: %s\n' "$message" >&2
  printf 'Remediation: %s\n' "$remediation" >&2
  exit "$code"
}

# The Godot executable inside an unpacked release folder; the tag defaults to the folder name.
cached_binary() {
  local dir="$1" tag="${2:-$(basename "$1")}"
  case "$(uname -s)" in
    Darwin) printf '%s\n' "$dir/Godot.app/Contents/MacOS/Godot" ;;
    *) printf '%s\n' "$dir/Godot_v${tag}_linux.x86_64" ;;
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

# Print the SHA-512 of a file (shasum on macOS, sha512sum elsewhere).
sha512_of() {
  if command -v sha512sum >/dev/null 2>&1; then
    sha512sum "$1" | cut -d ' ' -f 1
  else
    shasum -a 512 "$1" | cut -d ' ' -f 1
  fi
}

download_godot() {
  local tag asset dest zip binary sums expected staging
  if ! tag="$(curl -fsSL "$latest_url" | python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])')" || [[ -z "$tag" ]]; then
    if binary="$(newest_cached)"; then
      printf 'WARNING: could not query the latest Godot release; using %s\n' "$binary" >&2
      printf '%s\n' "$binary"
      return 0
    fi
    die 3 "Install Godot 4 or set GODOT_BIN, or rerun with network access to GitHub." "could not query the latest Godot release from $latest_url"
  fi
  [[ "$tag" =~ ^[0-9]+(\.[0-9]+)*-stable$ ]] \
    || die 3 "Install Godot 4 and set GODOT_BIN, or rerun later." "the latest Godot release tag is not a stable version: $tag"
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
  # Download and unpack into a private staging folder, check the archive against the release's
  # SHA512-SUMS.txt, then move it into place in one step, so a parallel run never sees a half
  # unpacked copy and a tampered download never runs.
  mkdir -p "$cache_root"
  staging="$(mktemp -d "$cache_root/.download.XXXXXX")"
  zip="$staging/$asset"
  sums="$staging/SHA512-SUMS.txt"
  printf 'Downloading %s into %s\n' "$asset" "$dest" >&2
  curl -fsSL -o "$zip" "https://github.com/godotengine/godot/releases/download/${tag}/${asset}" \
    || { rm -rf "$staging"; die 3 "Check network access to GitHub, or install Godot 4 and set GODOT_BIN." "could not download $asset"; }
  curl -fsSL -o "$sums" "https://github.com/godotengine/godot/releases/download/${tag}/SHA512-SUMS.txt" \
    || { rm -rf "$staging"; die 3 "Check network access to GitHub, or install Godot 4 and set GODOT_BIN." "could not download SHA512-SUMS.txt for $tag"; }
  expected="$(awk -v name="$asset" '$2 == name { print $1 }' "$sums")"
  if [[ -z "$expected" || "$(sha512_of "$zip")" != "$expected" ]]; then
    rm -rf "$staging"
    die 3 "Rerun to download again, or install Godot 4 and set GODOT_BIN." "$asset does not match its SHA-512 in SHA512-SUMS.txt"
  fi
  unzip -q -o "$zip" -d "$staging/unpacked" \
    || { rm -rf "$staging"; die 3 "Rerun, or install Godot 4 and set GODOT_BIN." "could not unpack $asset"; }
  if [[ ! -x "$(cached_binary "$staging/unpacked" "$tag")" ]]; then
    rm -rf "$staging"
    die 3 "Rerun, or install Godot 4 and set GODOT_BIN." "the download did not contain $(basename "$binary")"
  fi
  # Another run may have finished first; either copy is the same verified release. A folder left
  # by an interrupted older download holds no binary and is replaced.
  if [[ ! -x "$binary" ]]; then
    rm -rf "$dest"
    mv "$staging/unpacked" "$dest" 2>/dev/null || true
  fi
  rm -rf "$staging"
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

python3 - "$project/Beep.wav" <<'PY'
import struct
import sys
import wave

with wave.open(sys.argv[1], "wb") as handle:
    handle.setnchannels(1)
    handle.setsampwidth(2)
    handle.setframerate(22050)
    handle.writeframes(b"".join(struct.pack("<h", (i % 50) * 400 - 10000) for i in range(2205)))
PY

# Compare an NMG_RESULT JSON with an expected file (or one key of it); floats within 0.001.
#   python3 "$compare" <result json> <expected.json> [key]
compare="$project/.nmg_compare.py"
cat >"$compare" <<'PY'
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
if len(sys.argv) > 3:
    expected = expected[sys.argv[3]]
problems = diff(actual, expected, "result")
for problem in problems:
    print(problem, file=sys.stderr)
raise SystemExit(1 if problems else 0)
PY

# Run Godot headless in the temp project, killing it after gate_timeout seconds (exit 124).
run_godot() {
  python3 - "$gate_timeout" "$godot" --headless --audio-driver Dummy --path "$project" "$@" <<'PY'
import subprocess
import sys

limit = float(sys.argv[1])
try:
    done = subprocess.run(sys.argv[2:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=limit)
except subprocess.TimeoutExpired as error:
    sys.stdout.write((error.stdout or b"").decode("utf-8", "replace"))
    print(f"NMG_GATE_TIMEOUT after {limit:g} s")
    sys.exit(124)
sys.stdout.write(done.stdout.decode("utf-8", "replace"))
sys.exit(done.returncode)
PY
}

# Fail with exit 10 when the last Godot run hit the timeout.
check_timeout() {
  local status="$1" what="$2"
  if (( status == 124 )); then
    die 10 "Check that Godot starts headless on this host (for example, that macOS has not quarantined it), or raise GODOT_GATE_TIMEOUT." "$what did not finish within $gate_timeout s"
  fi
}

# 1. Import the fixture project.
status=0
output="$(run_godot --import)" || status=$?
printf '%s\n' "$output"
check_timeout "$status" "the fixture import"
if (( status != 0 )) || grep -q '^ERROR:' <<<"$output"; then
  first="$(grep -m 1 '^ERROR:' <<<"$output" || true)"
  die 4 "Read the import output above and fix the fixture or the add-on, then rerun." "fixture import failed (exit $status) ${first}"
fi

# 2. Run the add-on tests.
status=0
output="$(run_godot -s res://addons/nmg_game_dev/tests/run_tests.gd)" || status=$?
printf '%s\n' "$output"
check_timeout "$status" "the add-on tests"
if (( status != 0 )) \
  || grep -qE '^(SCRIPT )?ERROR:' <<<"$output" \
  || ! grep -qE '^[0-9]+ passed, 0 failed$' <<<"$output"; then
  die 5 "Fix the failing add-on test or script error reported above, then rerun." "add-on tests failed (exit $status)"
fi
for test in "${required_tests[@]}"; do
  if ! grep -qxF "PASS $test" <<<"$output"; then
    die 5 "Restore the add-on test $test in its tests/ file, then rerun." "add-on tests failed: no PASS line for $test"
  fi
done

# 3. Probe the fixture Crate.glb and compare with the expected result.
probe_dir="$project/.godot/nmg_probes"
mkdir -p "$probe_dir"
cp "$probe" "$probe_dir/probe_asset.gd"
params="$probe_dir/probe_asset.params.json"
printf '{"glb": "res://Crate.glb"}\n' >"$params"
status=0
output="$(run_godot -s res://.godot/nmg_probes/probe_asset.gd -- "$params")" || status=$?
printf '%s\n' "$output"
check_timeout "$status" "probe_asset.gd"
result="$(grep '^NMG_RESULT ' <<<"$output" | tail -n 1 || true)"
if (( status != 0 )) || [[ -z "$result" ]]; then
  die 6 "Read the probe output above; check that the fixture imported and probe_asset.gd parses." "probe_asset.gd failed (exit $status) or printed no NMG_RESULT line"
fi

if ! python3 "$compare" "${result#NMG_RESULT }" "$fixture/expected-probe.json"
then
  die 7 "Fix the probe or the importer, or regenerate the fixture with tests/godot/make_crate_glb.py and update expected-probe.json." "the probe result differs from tests/godot/fixture/expected-probe.json"
fi

# 4. Every probe script must parse.
for source in "$probes"/*.gd; do
  name="$(basename "$source")"
  cp "$source" "$probe_dir/$name"
  status=0
  output="$(run_godot --check-only -s "res://.godot/nmg_probes/$name")" || status=$?
  printf '%s\n' "$output"
  check_timeout "$status" "--check-only $name"
  if (( status != 0 )) || grep -qE '^(SCRIPT |Parse )?ERROR:' <<<"$output"; then
    die 8 "Fix the GDScript error in src/nmg_game_dev/godot/gd/$name reported above, then rerun." "$name failed --check-only (exit $status)"
  fi
done

# 5. Smoke-run the other probes and check each result has the shape the Python side reads.
smoke() {
  local name="$1" params_json="$2" check="$3" params_file result
  params_file="$probe_dir/${name%.gd}.params.json"
  printf '%s\n' "$params_json" >"$params_file"
  status=0
  output="$(run_godot -s "res://.godot/nmg_probes/$name" -- "$params_file")" || status=$?
  printf '%s\n' "$output"
  check_timeout "$status" "$name"
  result="$(grep '^NMG_RESULT ' <<<"$output" | tail -n 1 || true)"
  if (( status != 0 )) || [[ -z "$result" ]] \
    || ! python3 -c "import json, sys; r = json.loads(sys.argv[1]); sys.exit(0 if ($check) else 1)" "${result#NMG_RESULT }"; then
    die 9 "Fix src/nmg_game_dev/godot/gd/$name so its NMG_RESULT matches what src/nmg_game_dev/godot/ reads, then rerun." "$name smoke run failed (exit $status) or printed the wrong result shape"
  fi
}
# Run a probe with the params in an expected file and require its "result" (floats within 0.001).
expect() {
  local name="$1" expected="$2" params_file result
  params_file="$probe_dir/${name%.gd}.expected.params.json"
  python3 -c 'import json, sys; json.dump(json.load(open(sys.argv[1]))["params"], open(sys.argv[2], "w"))' \
    "$expected" "$params_file"
  status=0
  output="$(run_godot -s "res://.godot/nmg_probes/$name" -- "$params_file")" || status=$?
  printf '%s\n' "$output"
  check_timeout "$status" "$name"
  result="$(grep '^NMG_RESULT ' <<<"$output" | tail -n 1 || true)"
  if (( status != 0 )) || [[ -z "$result" ]] \
    || ! python3 "$compare" "${result#NMG_RESULT }" "$expected" result; then
    die 9 "Fix src/nmg_game_dev/godot/gd/$name or its writer, or regenerate the fixture with tests/godot/make_probe_fixtures.py, then rerun." "$name result differs from tests/godot/fixture/$(basename "$expected") (exit $status)"
  fi
}
expect probe_anims.gd "$fixture/expected-anims.json"
expect probe_terrain.gd "$fixture/expected-terrain.json"
smoke probe_terrain.gd '{"mode": "meshes", "glbs": ["res://Crate.glb"]}' \
  'isinstance(r["meshes"]["res://Crate.glb"], list) and len(r["meshes"]["res://Crate.glb"]) >= 1'
smoke probe_audio.gd '{"stream": "res://Beep.wav"}' \
  'r["class"] == "AudioStreamWAV" and isinstance(r["loop_mode"], int)'

echo "gate-godot-headless: import, add-on tests, and probes passed"
