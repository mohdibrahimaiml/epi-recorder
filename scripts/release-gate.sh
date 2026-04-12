#!/usr/bin/env bash
# Linux/macOS equivalent of release-gate.ps1
set -euo pipefail

PYTHON="${1:-python}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
GATE_ROOT="${REPO_ROOT}/.tmp-release-gate/${RUN_ID}"
BASE_TEMP="${GATE_ROOT}/pytest"
DIST_DIR="${GATE_ROOT}/dist"

mkdir -p "${BASE_TEMP}" "${DIST_DIR}"
rm -rf "${REPO_ROOT}/build"

echo "== EPI Release Gate =="
echo "Repo: ${REPO_ROOT}"
echo "Python: ${PYTHON}"
echo ""

"${PYTHON}" -m epi_cli.main version
"${PYTHON}" -m pytest tests/test_version_consistency_runtime.py tests/test_truth_consistency.py -q --basetemp "${BASE_TEMP}"
"${PYTHON}" -m pytest tests -q --maxfail=20 --basetemp "${BASE_TEMP}"

"${PYTHON}" -m build --no-isolation --sdist --wheel --outdir "${DIST_DIR}"
"${PYTHON}" -m twine check "${DIST_DIR}"/*

SDIST_FILE="$(ls "${DIST_DIR}"/*.tar.gz 2>/dev/null | head -1)"
if [ -z "${SDIST_FILE}" ]; then
    echo "Failed: no source distribution artifacts found for audit" >&2
    exit 1
fi
"${PYTHON}" "${REPO_ROOT}/scripts/audit_sdist.py" "${SDIST_FILE}"

WHEEL_FILE="$(ls "${DIST_DIR}"/*.whl 2>/dev/null | head -1)"
if [ -z "${WHEEL_FILE}" ]; then
    echo "Failed: no wheel artifacts found for audit" >&2
    exit 1
fi
"${PYTHON}" "${REPO_ROOT}/scripts/audit_wheel.py" "${WHEEL_FILE}"

echo ""
echo "Release gate PASSED. Artifacts in: ${DIST_DIR}"
