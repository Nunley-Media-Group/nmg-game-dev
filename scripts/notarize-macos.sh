#!/usr/bin/env bash
# Notarize the signed macOS app and staple the ticket (#6, FR4, AC1, AC2, AC9).
#
#   scripts/notarize-macos.sh <app> [--dry-run]
#
# Outside --dry-run it needs NOTARIZATION_APPLE_ID, NOTARIZATION_APP_SPECIFIC_PASSWORD, and
# NOTARIZATION_TEAM_ID. It zips the app, submits the zip with notarytool --wait, requires
# "status: Accepted" in the output, then staples. The app-specific password and Apple ID are shown
# as *** and never printed.
# Exit 0 when accepted and stapled, 1 when submission or staple fails or the status is not
# Accepted, 2 on bad arguments or a missing variable or tool, each with a Remediation: line.
# --dry-run prints the plan, submits nothing, and exits 0.
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
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    -*)
      die 2 "Use <app> [--dry-run]." "unknown option: $1"
      ;;
    *)
      [[ -z "$app" ]] || die 2 "Pass exactly one .app path." "more than one app path was given"
      app="$1"
      shift
      ;;
  esac
done

[[ -n "$app" ]] || die 2 "Pass the path to the signed .app." "no .app path was given"

apple_id="${NOTARIZATION_APPLE_ID:-}"
password="${NOTARIZATION_APP_SPECIFIC_PASSWORD:-}"
team="${NOTARIZATION_TEAM_ID:-}"

if (( dry_run )); then
  team="${team:-<NOTARIZATION_TEAM_ID>}"
else
  for name in NOTARIZATION_APPLE_ID NOTARIZATION_APP_SPECIFIC_PASSWORD NOTARIZATION_TEAM_ID; do
    [[ -n "${!name:-}" ]] || die 2 "Set ${name}, then rerun the macOS ship." "${name} is not set"
  done
  [[ -d "$app" ]] || die 2 "Sign the .app first, or pass the path that the signed .app is at." "app bundle not found: $app"
  command -v ditto >/dev/null || die 2 "Install the Xcode command line tools so ditto is on PATH." "ditto not found on PATH"
  command -v xcrun >/dev/null || die 2 "Install the Xcode command line tools so xcrun is on PATH." "xcrun not found on PATH"
fi

zip="${app%/}.zip"
ditto_cmd=(ditto -c -k --keepParent "$app" "$zip")
submit_cmd=(xcrun notarytool submit "$zip" --apple-id "$apple_id" --password "$password" --team-id "$team" --wait)
shown_submit=(xcrun notarytool submit "$zip" --apple-id '***' --password '***' --team-id "$team" --wait)
staple_cmd=(xcrun stapler staple "$app")

if (( dry_run )); then
  show "DRY-RUN:" "${ditto_cmd[@]}"
  echo "DRY-RUN: notarization pass (no submission) for team ${team}"
  show "DRY-RUN:" "${staple_cmd[@]}"
  exit 0
fi

show "RUN:" "${ditto_cmd[@]}"
"${ditto_cmd[@]}" || die 1 "Check that the signed .app is readable and that its folder is writable, then rerun." "ditto could not zip $app"
show "RUN:" "${shown_submit[@]}"
if ! output="$("${submit_cmd[@]}" 2>&1)"; then
  printf '%s\n' "$output"
  die 1 "Read the notarytool output above, fix the reported problem, and rerun the macOS ship." "notarytool submit failed for $zip"
fi
printf '%s\n' "$output"
grep -q 'status: Accepted' <<<"$output" || die 1 "Read the notarytool log for the submission, fix the rejection, and rerun the macOS ship." "notarization was not accepted"
show "RUN:" "${staple_cmd[@]}"
"${staple_cmd[@]}" || die 1 "Check that the accepted ticket can be stapled to the .app, then rerun the macOS ship." "stapler failed for $app"
echo "Notarized and stapled $app"
