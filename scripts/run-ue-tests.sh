#!/usr/bin/env bash
# scripts/run-ue-tests.sh — Run NmgGameDev UE Automation Spec tests headlessly.
#
# Usage (from repo root):  scripts/run-ue-tests.sh
#
# Env:  UE_ROOT  Override the UE 5.7 install path. Default: /Users/Shared/Epic Games/UE_5.7
#
# Exit: 0 pass; 1 failure (failing test lines on stderr); 2 prerequisite missing.
# Output: tests/ue-automation/results.xml (JUnit XML, consumed by gate-ue-automation).
#
# UE 5.7 writes its native report (index.json + index.html) into the -ReportExportPath
# directory rather than a JUnit file. This script converts that JSON into JUnit XML so
# gate-ue-automation has a stable artifact shape.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

UE_ROOT="${UE_ROOT:-/Users/Shared/Epic Games/UE_5.7}"

if [[ ! -d "${UE_ROOT}" ]]; then
    echo "ERROR: Unreal Engine 5.7 not found at '${UE_ROOT}'." >&2
    echo "Remediation: Install UE 5.7 or set UE_ROOT to the correct path." >&2
    exit 2
fi

case "$(uname -s)" in
    Darwin*)                          UE_HOST_DIR="Mac" ;;
    Linux*)                           UE_HOST_DIR="Linux" ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT)  UE_HOST_DIR="Win64" ;;
    *)
        echo "ERROR: Unsupported platform '$(uname -s)'." >&2
        exit 2
        ;;
esac

UE_CMD="${UE_ROOT}/Engine/Binaries/${UE_HOST_DIR}/UnrealEditor-Cmd"
if [[ "${UE_HOST_DIR}" == "Win64" ]]; then
    UE_CMD="${UE_CMD}.exe"
fi

if [[ ! -x "${UE_CMD}" ]]; then
    echo "ERROR: UnrealEditor-Cmd not found at '${UE_CMD}'." >&2
    echo "Remediation: Verify your UE 5.7 install is complete, or set UE_ROOT correctly." >&2
    exit 2
fi

PROJECT_FILE="${REPO_ROOT}/fixtures/dogfood.uproject"
if [[ ! -f "${PROJECT_FILE}" ]]; then
    echo "ERROR: Dogfood fixture not found at '${PROJECT_FILE}'." >&2
    echo "Remediation: Ensure fixtures/dogfood.uproject exists (created by issue #1)." >&2
    exit 2
fi

UBT_SCRIPT="${UE_ROOT}/Engine/Build/BatchFiles/${UE_HOST_DIR}/Build.sh"
if [[ "${UE_HOST_DIR}" == "Win64" ]]; then
    UBT_SCRIPT="${UE_ROOT}/Engine/Build/BatchFiles/Build.bat"
fi

REPORT_DIR="${REPO_ROOT}/tests/ue-automation"
REPORT_INDEX_DIR="${REPORT_DIR}/index"
REPORT_XML="${REPORT_DIR}/results.xml"
mkdir -p "${REPORT_DIR}"
rm -rf "${REPORT_INDEX_DIR}" "${REPORT_XML}"

echo "Building DogfoodEditor target (compiles nmg-game-dev plugin against the fixture)..."
"${UBT_SCRIPT}" DogfoodEditor "${UE_HOST_DIR}" Development -Project="${PROJECT_FILE}" -WaitMutex >&2
echo ""

echo "Running NmgGameDev.* automation tests against ${PROJECT_FILE} ..."
echo "UE install: ${UE_CMD}"
echo "Native report dir: ${REPORT_INDEX_DIR}"
echo "JUnit report: ${REPORT_XML}"
echo ""

UE_EXIT=0
"${UE_CMD}" \
    "${PROJECT_FILE}" \
    -ExecCmds="Automation RunTests NmgGameDev.+; Quit" \
    -unattended \
    -nopause \
    -nullrhi \
    -ReportOutputPath="${REPORT_INDEX_DIR}" \
    -ReportExportPath="${REPORT_INDEX_DIR}" || UE_EXIT=$?

INDEX_JSON="${REPORT_INDEX_DIR}/index.json"
if [[ ! -f "${INDEX_JSON}" ]]; then
    echo "ERROR: Native report index not produced at '${INDEX_JSON}'." >&2
    echo "This usually means UnrealEditor-Cmd crashed or could not load the project." >&2
    exit 2
fi

# Convert UE's native JSON index into JUnit XML. UE 5.7 writes UTF-8-BOM.
python3 - "${INDEX_JSON}" "${REPORT_XML}" <<'PY'
import json
import sys
from xml.sax.saxutils import escape

index_path, xml_path = sys.argv[1], sys.argv[2]
with open(index_path, encoding="utf-8-sig") as f:
    data = json.load(f)

tests = data.get("tests", [])
total = len(tests)
failures = sum(1 for t in tests if t.get("state") != "Success")
duration = sum(float(t.get("duration", 0.0)) for t in tests)

lines = ['<?xml version="1.0" encoding="UTF-8"?>']
lines.append(
    f'<testsuite name="NmgGameDev" tests="{total}" failures="{failures}" '
    f'errors="0" skipped="0" time="{duration:.3f}">'
)
for t in tests:
    name = escape(t.get("testDisplayName", ""))
    classname = escape(".".join(t.get("fullTestPath", "").split(".")[:-1]) or "NmgGameDev")
    t_time = float(t.get("duration", 0.0))
    lines.append(f'  <testcase classname="{classname}" name="{name}" time="{t_time:.3f}">')
    if t.get("state") != "Success":
        msgs = [escape(str(e.get("event", {}).get("message", ""))) for e in t.get("entries", [])]
        lines.append(f'    <failure message="{escape(t.get("state",""))}">{" | ".join(msgs)}</failure>')
    lines.append('  </testcase>')
lines.append('</testsuite>')

with open(xml_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
    f.write("\n")
PY

FAILED_COUNT="$(python3 -c "import json; d=json.load(open('${INDEX_JSON}', encoding='utf-8-sig')); print(d.get('failed', 0))")"

if [[ "${FAILED_COUNT}" -gt 0 || "${UE_EXIT}" -ne 0 ]]; then
    echo "FAILED: ${FAILED_COUNT} test failure(s). JUnit report: ${REPORT_XML}" >&2
    echo "" >&2
    echo "Failing tests:" >&2
    python3 -c "
import json
d = json.load(open('${INDEX_JSON}', encoding='utf-8-sig'))
for t in d.get('tests', []):
    if t.get('state') != 'Success':
        print('  -', t.get('fullTestPath', '<unknown>'))
" >&2
    exit 1
fi

echo ""
echo "All NmgGameDev.* tests passed. JUnit report: ${REPORT_XML}"
