#!/usr/bin/env bash
# Sign the archived macOS app with the hardened runtime, then verify the signature (#6, FR4, AC1).
#
#   scripts/sign-macos.sh <app> --identity <id> [--dry-run]
#
# Exit 0 when signed and verified, 1 when codesign fails, 2 on bad arguments or a missing app or
# codesign, each with a Remediation: line. --dry-run prints the DRY-RUN: commands, runs nothing,
# and exits 0.
set -euo pipefail

die() {
  local code="$1" remediation="$2" message="$3"
  printf 'ERROR: %s\n' "$message" >&2
  printf 'Remediation: %s\n' "$remediation" >&2
  exit "$code"
}

show() {
  local prefix="$1" line arg
  shift
  line="$prefix"
  for arg in "$@"; do
    line+=" $arg"
  done
  printf '%s\n' "$line"
}

app=""
identity=""
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --identity)
      [[ $# -ge 2 ]] || die 2 "Pass --identity with the Developer ID Application identity." "--identity needs a value"
      identity="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -*)
      die 2 "Use <app> --identity <id> [--dry-run]." "unknown option: $1"
      ;;
    *)
      [[ -z "$app" ]] || die 2 "Pass exactly one .app path." "more than one app path was given"
      app="$1"
      shift
      ;;
  esac
done

[[ -n "$app" ]] || die 2 "Pass the path to the archived .app." "no .app path was given"
[[ -n "$identity" ]] || die 2 "Pass --identity with the Developer ID Application identity for the team." "--identity is required"

if (( ! dry_run )); then
  [[ -d "$app" ]] || die 2 "Build the macOS app first, or pass the .app that UAT archived." "app bundle not found: $app"
  command -v codesign >/dev/null || die 2 "Install the Xcode command line tools so codesign is on PATH." "codesign not found on PATH"
fi

sign_cmd=(codesign --force --deep --options runtime --timestamp --sign "$identity" "$app")
verify_cmd=(codesign --verify --strict --verbose=2 "$app")

if (( dry_run )); then
  show "DRY-RUN:" "${sign_cmd[@]}"
  show "DRY-RUN:" "${verify_cmd[@]}"
  exit 0
fi

show "RUN:" "${sign_cmd[@]}"
"${sign_cmd[@]}" || die 1 "Check the signing identity in Keychain Access and that the .app is intact, then rerun the macOS ship." "codesign failed for $app"
show "RUN:" "${verify_cmd[@]}"
"${verify_cmd[@]}" || die 1 "Rebuild the .app, then sign it again; the signature did not verify." "codesign verification failed for $app"
echo "Signed and verified $app"
