#!/usr/bin/env bash
# Cook-manifest gate (#6, FR5, AC4): fail when a cooked package carries the other variant's Content/ paths.
#
#   scripts/verify-cook-manifest.sh --variant desktop|mobile [--dry-run] <dir-or-listing-file>
#
# Exit 0 when the package is clean. Exit 1 prints each cross-variant path on stdout and a
# Remediation: line on stderr. Exit 2 names the bad argument or missing path on stderr, with a
# Remediation: line. --dry-run validates the arguments and prints the planned check without
# reading the package.
set -euo pipefail

usage() {
  echo "Usage: scripts/verify-cook-manifest.sh --variant desktop|mobile [--dry-run] <dir-or-listing-file>"
}

die() {
  local code="$1" remediation="$2" message="$3"
  printf 'ERROR: %s\n' "$message" >&2
  printf 'Remediation: %s\n' "$remediation" >&2
  exit "$code"
}

variant=""
target=""
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --variant)
      [[ $# -ge 2 ]] || die 2 "Pass --variant desktop or --variant mobile." "--variant needs a value"
      variant="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    -*)
      die 2 "Pass --variant, --dry-run, or one cooked directory or listing file." "unknown option: $1"
      ;;
    *)
      [[ -z "$target" ]] || die 2 "Pass exactly one cooked directory or listing file." "more than one target was given"
      target="$1"
      shift
      ;;
  esac
done

case "$variant" in
  desktop) forbidden='(^|/)Content/(.+/)?Mobile/' ;;
  mobile) forbidden='(^|/)Content/(.+/)?Desktop/' ;;
  *) die 2 "Pass --variant desktop or --variant mobile." "missing or invalid --variant: '${variant}'" ;;
esac

[[ -n "$target" ]] || die 2 "Pass the cooked directory or the listing file to check." "no directory or listing file was given"
[[ -e "$target" ]] || die 2 "Check the path, or rerun the build so the cooked output exists." "path not found: $target"

if (( dry_run )); then
  echo "DRY-RUN: verify cook manifest --variant ${variant} ${target}"
  exit 0
fi

# Windows listings use backslashes; '\134' is the backslash, written in octal to keep it literal.
if [[ -d "$target" ]]; then
  paths="$(find "$target" -type f | tr '\134' '/')"
else
  paths="$(tr '\134' '/' < "$target")"
fi

offenders="$(printf '%s\n' "$paths" | grep -E "$forbidden" || true)"

if [[ -n "$offenders" ]]; then
  echo "FAIL: the ${variant} package lists cross-variant Content/ paths:"
  printf '%s\n' "$offenders"
  if [[ "$variant" == "mobile" ]]; then
    printf 'Remediation: %s\n' "Exclude Content/**/Desktop/ from the Mobile cook rules, then recook the mobile package." >&2
  else
    printf 'Remediation: %s\n' "Exclude Content/**/Mobile/ from the Desktop cook rules, then recook the desktop package." >&2
  fi
  exit 1
fi

echo "PASS: no cross-variant Content/ paths in the ${variant} package"
