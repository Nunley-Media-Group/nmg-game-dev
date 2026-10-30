#!/usr/bin/env bash
# Build and archive the Android .aab with UAT BuildCookRun (#6, FR3, AC3).
#
#   scripts/build-android.sh --project <uproject> --archive <dir> [--dry-run]
#
# Requires ANDROID_KEYSTORE and ANDROID_KEYSTORE_PASSWORD outside --dry-run. ANDROID_KEYSTORE_ALIAS
# defaults to "upload". The keystore password never goes on UAT's command line, which UAT logs at
# startup. For the run only, it goes into the project's Config/UserEngine.ini, the last config
# layer UE reads; the file's previous state is restored on exit. UAT's output is also redacted, and
# the password shows as *** in every printed line. The block sits between BEGIN and END
# nmg-game-dev ship markers, so every run (dry or real) first removes a block that a killed or
# crashed run left behind. In a git repo, a real run refuses to write the file unless git ignores it.
# Exit 0 on success, 1 when UAT fails, 2 on bad arguments, a missing variable, a missing RunUAT.sh,
# or a UserEngine.ini that git tracks or does not ignore, each with a Remediation: line. --dry-run runs nothing and exits 0. UE_ROOT overrides
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
project_dir="$(dirname "$project")"
user_ini="${project_dir}/Config/UserEngine.ini"
begin_marker="; BEGIN nmg-game-dev ship"
end_marker="; END nmg-game-dev ship"

# Remove a password block that an interrupted run left behind, then delete the file if nothing else
# was in it.
if [[ -f "$user_ini" ]] && grep -qxF -- "$begin_marker" "$user_ini"; then
  stripped="$(mktemp "${TMPDIR:-/tmp}/nmg-user-engine.XXXXXX")"
  awk -v begin="$begin_marker" -v end="$end_marker" \
    '$0 == begin { skip = 1; next } skip && $0 == end { skip = 0; next } !skip' \
    "$user_ini" >"$stripped"
  if [[ -s "$stripped" ]]; then
    cat "$stripped" >"$user_ini"
    rm -f "$stripped"
  else
    rm -f "$stripped" "$user_ini"
  fi
  printf 'Removed a KeyStorePassword block left in %s by an interrupted ship run.\n' "$user_ini"
fi
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

if git -C "$project_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git -C "$project_dir" ls-files --error-unmatch -- Config/UserEngine.ini >/dev/null 2>&1; then
    die 2 "Run 'git rm --cached Config/UserEngine.ini', add Config/UserEngine.ini to the project's .gitignore, then rerun." \
      "Config/UserEngine.ini is tracked by git; the ship will not write the keystore password into it"
  fi
  if ! git -C "$project_dir" check-ignore -q -- Config/UserEngine.ini; then
    die 2 "Add Config/UserEngine.ini to the project's .gitignore, then rerun." \
      "Config/UserEngine.ini is not ignored by git; the ship will not write the keystore password into it"
  fi
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
      # Keep the block on its own lines so a leftover cleanup restores the file exactly.
      if [[ -s "$backup" && -n "$(tail -c 1 "$backup")" ]]; then
        printf '\n'
      fi
    fi
    printf '%s\n%s\nKeyStorePassword=%s\n%s\n' "$begin_marker" "$section" "$password" "$end_marker"
  } >"$user_ini"
)

show "RUN:" "write ${section} KeyStorePassword=*** to ${user_ini} for the run"
show "RUN:" "${cmd[@]}"
"${cmd[@]}" 2>&1 | redact || die 1 "Read the UAT log above, fix the reported error, and rerun the Android ship." "RunUAT BuildCookRun failed for Android"
echo "Archived Android build to $archive"
