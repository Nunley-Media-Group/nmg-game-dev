#!/usr/bin/env bash
# Build and archive the Android .aab with UAT BuildCookRun (#6, FR3, AC3).
#
#   scripts/build-android.sh --project <uproject> --archive <dir> [--dry-run]
#
# Requires ANDROID_KEYSTORE and ANDROID_KEYSTORE_PASSWORD outside --dry-run. ANDROID_KEYSTORE_ALIAS
# defaults to "upload". The keystore password never goes on UAT's command line, which UAT logs at
# startup. For the run only, it goes into the project's Config/UserEngine.ini, the last config
# layer UE reads; the file's previous state is restored on exit. UAT's output is also redacted, and
# the password shows as *** in every printed line.
# Exit 0 on success, 1 when UAT fails, 2 on bad arguments, a missing variable, or a missing
# RunUAT.sh, each with a Remediation: line. --dry-run runs nothing and exits 0. UE_ROOT overrides
# the engine location.
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

keystore="${ANDROID_KEYSTORE:-}"
password="${ANDROID_KEYSTORE_PASSWORD:-}"
alias_name="${ANDROID_KEYSTORE_ALIAS:-upload}"
if (( ! dry_run )); then
  [[ -n "$keystore" ]] || die 2 "Set ANDROID_KEYSTORE to the upload keystore path, then rerun." "ANDROID_KEYSTORE is not set"
  [[ -n "$password" ]] || die 2 "Set ANDROID_KEYSTORE_PASSWORD, then rerun." "ANDROID_KEYSTORE_PASSWORD is not set"
fi
[[ -n "$keystore" ]] || keystore="<ANDROID_KEYSTORE>"
[[ -n "$password" ]] || password="<ANDROID_KEYSTORE_PASSWORD>"

runuat="${UE_ROOT}/Engine/Build/BatchFiles/RunUAT.sh"
if (( ! dry_run )); then
  [[ -f "$project" ]] || die 2 "Pass the path to an existing .uproject file." "project file not found: $project"
  [[ -x "$runuat" ]] || die 2 "Set UE_ROOT to the Unreal Engine 5.8 install that holds Engine/Build/BatchFiles/RunUAT.sh." "RunUAT.sh not found or not executable under UE_ROOT"
fi

section="[/Script/AndroidRuntimeSettings.AndroidRuntimeSettings]"
user_ini="$(dirname "$project")/Config/UserEngine.ini"
cmd=(
  "$runuat" BuildCookRun
  "-project=${project}" -platform=Android -clientconfig=Shipping
  -build -cook -stage -pak -package -archive
  "-archivedirectory=${archive}"
  -unattended -utf8output -nop4
  -distribution
  "-ini:Engine:${section}:bEnableBundle=True,KeyStore=${keystore},KeyAlias=${alias_name}"
)

if (( dry_run )); then
  show "DRY-RUN:" "write ${section} KeyStorePassword=*** to ${user_ini} for the run"
  show "DRY-RUN:" "${cmd[@]}"
  exit 0
fi

backup=""
restore_user_ini() {
  if [[ -n "$backup" ]]; then
    mv -f "$backup" "$user_ini"
  else
    rm -f "$user_ini"
  fi
}

redact() {
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    printf '%s\n' "${line//"$password"/***}"
  done
}

mkdir -p "$archive" "$(dirname "$user_ini")"
if [[ -f "$user_ini" ]]; then
  backup="$(mktemp "${TMPDIR:-/tmp}/nmg-user-engine.XXXXXX")"
  cp -p "$user_ini" "$backup"
fi
trap restore_user_ini EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
rm -f "$user_ini"
(
  umask 077
  {
    if [[ -n "$backup" ]]; then
      cat "$backup"
    fi
    printf '\n%s\nKeyStorePassword=%s\n' "$section" "$password"
  } >"$user_ini"
)

show "RUN:" "write ${section} KeyStorePassword=*** to ${user_ini} for the run"
show "RUN:" "${cmd[@]}"
"${cmd[@]}" 2>&1 | redact || die 1 "Read the UAT log above, fix the reported error, and rerun the Android ship." "RunUAT BuildCookRun failed for Android"
echo "Archived Android build to $archive"
