#!/usr/bin/env bash
# Build the Windows target on the remote host over SSH, then copy the packaged folder back (#6, FR3, AC5).
#
#   scripts/build-windows.sh --archive <local dir> --listing <file> [--dry-run]
#
# Remote settings: WINDOWS_BUILD_HOST, WINDOWS_BUILD_USER, WINDOWS_BUILD_SSH_KEY (a key file), and
# WINDOWS_REMOTE_PROJECT_PATH (the remote .uproject). WINDOWS_UE_ROOT overrides the remote engine.
# The cooked-file listing is written to --listing for the cook-manifest gate. The packaged Windows
# folder is copied into <archive>/Windows. Exit 0 on success, 1 when a remote step fails, 2 on bad
# arguments or a missing setting, each with a Remediation: line. --dry-run prints the DRY-RUN:
# commands, runs nothing, and exits 0.
set -euo pipefail

WINDOWS_UE_ROOT="${WINDOWS_UE_ROOT:-C:\\Program Files\\Epic Games\\UE_5.8}"

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

archive=""
listing=""
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive)
      [[ $# -ge 2 ]] || die 2 "Pass --archive with the local output directory." "--archive needs a value"
      archive="$2"
      shift 2
      ;;
    --listing)
      [[ $# -ge 2 ]] || die 2 "Pass --listing with the file to write the cooked listing to." "--listing needs a value"
      listing="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    *)
      die 2 "Use --archive <dir> --listing <file> [--dry-run]." "unknown argument: $1"
      ;;
  esac
done

[[ -n "$archive" ]] || die 2 "Pass --archive with the local output directory." "--archive is required"
[[ -n "$listing" ]] || die 2 "Pass --listing with the file to write the cooked listing to." "--listing is required"

host="${WINDOWS_BUILD_HOST:-}"
user="${WINDOWS_BUILD_USER:-}"
key="${WINDOWS_BUILD_SSH_KEY:-}"
project="${WINDOWS_REMOTE_PROJECT_PATH:-}"

if (( dry_run )); then
  host="${host:-<WINDOWS_BUILD_HOST>}"
  user="${user:-<WINDOWS_BUILD_USER>}"
  key="${key:-<WINDOWS_BUILD_SSH_KEY>}"
  project="${project:-<WINDOWS_REMOTE_PROJECT_PATH>}"
else
  [[ -n "$host" ]] || die 2 "Set WINDOWS_BUILD_HOST to the Windows build host, then rerun." "WINDOWS_BUILD_HOST is not set"
  [[ -n "$user" ]] || die 2 "Set WINDOWS_BUILD_USER to the account on the build host, then rerun." "WINDOWS_BUILD_USER is not set"
  [[ -n "$key" && -r "$key" ]] || die 2 "Set WINDOWS_BUILD_SSH_KEY to a readable SSH private key file, then rerun." "WINDOWS_BUILD_SSH_KEY is unset or not readable"
  [[ -n "$project" ]] || die 2 "Set WINDOWS_REMOTE_PROJECT_PATH to the .uproject path on the build host, then rerun." "WINDOWS_REMOTE_PROJECT_PATH is not set"
  command -v ssh >/dev/null || die 2 "Install OpenSSH so ssh is on PATH." "ssh not found on PATH"
  command -v scp >/dev/null || die 2 "Install OpenSSH so scp is on PATH." "scp not found on PATH"
fi

remote_dir="${project%\\*}"
remote_uat="${WINDOWS_UE_ROOT}\\Engine\\Build\\BatchFiles\\RunUAT.bat"
remote_archive="${remote_dir}\\Saved\\NmgShip"
remote_cooked="${remote_dir}\\Saved\\Cooked\\Windows"

build_remote="\"${remote_uat}\" BuildCookRun \"-project=${project}\" -platform=Win64 -clientconfig=Shipping -build -cook -stage -pak -package -archive \"-archivedirectory=${remote_archive}\" -unattended -utf8output -nop4"
list_remote="cmd /c dir /s /b \"${remote_cooked}\""

ssh_build=(ssh -i "$key" -o BatchMode=yes "${user}@${host}" "$build_remote")
ssh_list=(ssh -i "$key" -o BatchMode=yes "${user}@${host}" "$list_remote")
scp_copy=(scp -i "$key" -r "${user}@${host}:${remote_archive}\\Windows" "$archive")

if (( dry_run )); then
  show "DRY-RUN:" "${ssh_build[@]}"
  show "DRY-RUN:" "${ssh_list[@]}" ">" "$listing"
  show "DRY-RUN:" "${scp_copy[@]}"
  exit 0
fi

mkdir -p "$archive"
show "RUN:" "${ssh_build[@]}"
"${ssh_build[@]}" || die 1 "Read the remote UAT output above, fix the reported error, and rerun the Windows ship." "RunUAT BuildCookRun failed on the Windows build host"
show "RUN:" "${ssh_list[@]}" ">" "$listing"
"${ssh_list[@]}" > "$listing" || die 1 "Check that the remote packaged folder exists, then rerun the Windows ship." "could not list the remote cooked files"
show "RUN:" "${scp_copy[@]}"
"${scp_copy[@]}" || die 1 "Check the connection to the Windows build host, then rerun the Windows ship." "could not copy the packaged folder back"
echo "Copied the Windows package to $archive/Windows"
