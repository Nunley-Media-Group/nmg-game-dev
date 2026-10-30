#!/usr/bin/env bash
# Build and archive the iOS .ipa with UAT BuildCookRun (#6, FR3, AC3).
#
#   scripts/build-ios.sh --project <uproject> --archive <dir> [--dry-run]
#
# Requires IOS_PROVISIONING_PROFILE outside --dry-run. Exit 0 on success, 1 when UAT fails, 2 on
# bad arguments, a missing variable, or a missing RunUAT.sh, each with a Remediation: line.
# --dry-run prints the DRY-RUN: command, runs nothing, and exits 0. UE_ROOT overrides the engine
# location.
set -euo pipefail

UE_ROOT="${UE_ROOT:-/Users/Shared/Epic Games/UE_5.8}"

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

project=""
archive=""
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      [[ $# -ge 2 ]] || die 2 "Pass --project with the .uproject path." "--project needs a value"
      project="$2"
      shift 2
      ;;
    --archive)
      [[ $# -ge 2 ]] || die 2 "Pass --archive with the output directory." "--archive needs a value"
      archive="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    *)
      die 2 "Use --project <uproject> --archive <dir> [--dry-run]." "unknown argument: $1"
      ;;
  esac
done

[[ -n "$project" ]] || die 2 "Pass --project with the .uproject path." "--project is required"
[[ -n "$archive" ]] || die 2 "Pass --archive with the directory UAT should archive into." "--archive is required"

profile="${IOS_PROVISIONING_PROFILE:-}"
if (( ! dry_run )); then
  [[ -n "$profile" ]] || die 2 "Set IOS_PROVISIONING_PROFILE to the .mobileprovision path, then rerun." "IOS_PROVISIONING_PROFILE is not set"
fi
profile_name="${profile##*/}"
[[ -n "$profile_name" ]] || profile_name="<IOS_PROVISIONING_PROFILE>"

runuat="${UE_ROOT}/Engine/Build/BatchFiles/RunUAT.sh"
if (( ! dry_run )); then
  [[ -f "$project" ]] || die 2 "Pass the path to an existing .uproject file." "project file not found: $project"
  [[ -x "$runuat" ]] || die 2 "Set UE_ROOT to the Unreal Engine 5.8 install that holds Engine/Build/BatchFiles/RunUAT.sh." "RunUAT.sh not found or not executable under UE_ROOT"
fi

cmd=(
  "$runuat" BuildCookRun
  "-project=${project}" -platform=IOS -clientconfig=Shipping
  -build -cook -stage -pak -package -archive
  "-archivedirectory=${archive}"
  -unattended -utf8output -nop4
  -distribution
  "-ini:Engine:[/Script/IOSRuntimeSettings.IOSRuntimeSettings]:MobileProvision=${profile_name}"
)

if (( dry_run )); then
  show "DRY-RUN:" "${cmd[@]}"
  exit 0
fi

mkdir -p "$archive"
show "RUN:" "${cmd[@]}"
"${cmd[@]}" || die 1 "Read the UAT log above, fix the reported error, and rerun the iOS ship." "RunUAT BuildCookRun failed for iOS"
echo "Archived iOS build to $archive"
