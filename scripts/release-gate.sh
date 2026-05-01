#!/usr/bin/env bash
# EPI Release Gate — Linux/macOS
# Usage: bash scripts/release-gate.sh [python]
# Default python: python3 (passed explicitly by CI as 'python')

set -euo pipefail

PYTHON="${1:-python3}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RUN_ID="$(date +%Y%m%d_%H%M%S)"
GATE_ROOT="${REPO_ROOT}/.tmp-release-gate/${RUN_ID}"
BASE_TEMP="${GATE_ROOT}/pytest"
BUILD_TEMP="${GATE_ROOT}/build-tmp"
DIST_DIR="${GATE_ROOT}/dist"
REPO_BUILD_DIR="${REPO_ROOT}/build"

mkdir -p "${BASE_TEMP}" "${BUILD_TEMP}" "${DIST_DIR}"

if [ -d "${REPO_BUILD_DIR}" ]; then
    rm -rf "${REPO_BUILD_DIR}"
fi

export TMPDIR="${BUILD_TEMP}"
export TMP="${BUILD_TEMP}"
export TEMP="${BUILD_TEMP}"

echo "== EPI Release Gate =="
echo "Repo: ${REPO_ROOT}"
echo "Python: ${PYTHON}"
echo ""

"${PYTHON}" -m epi_cli.main version
"${PYTHON}" -m pytest tests/test_version_consistency_runtime.py tests/test_truth_consistency.py \
    -q --basetemp "${BASE_TEMP}"
"${PYTHON}" -m pytest tests -q --maxfail=20 --basetemp "${BASE_TEMP}"

if ! "${PYTHON}" -m build --no-isolation --sdist --wheel --outdir "${DIST_DIR}"; then
    if [ -d "${DIST_DIR}" ]; then
        rm -f "${DIST_DIR}"/* || true
    fi
    echo "build failed in this environment; falling back to setup.py artifacts..."
    "${PYTHON}" setup.py bdist_wheel --dist-dir "${DIST_DIR}"
    "${PYTHON}" setup.py sdist --dist-dir "${DIST_DIR}"
fi

"${PYTHON}" -m twine check "${DIST_DIR}"/*


SDIST_FILES=("${DIST_DIR}"/*.tar.gz)
if [ ${#SDIST_FILES[@]} -eq 0 ] || [ ! -f "${SDIST_FILES[0]}" ]; then
    echo "ERROR: no source distribution artifacts found for audit" >&2
    exit 1
fi
"${PYTHON}" "${REPO_ROOT}/scripts/audit_sdist.py" "${SDIST_FILES[@]}"

WHEEL_FILES=("${DIST_DIR}"/*.whl)
if [ ${#WHEEL_FILES[@]} -eq 0 ] || [ ! -f "${WHEEL_FILES[0]}" ]; then
    echo "ERROR: no wheel artifacts found for audit" >&2
    exit 1
fi
"${PYTHON}" "${REPO_ROOT}/scripts/audit_wheel.py" "${WHEEL_FILES[@]}"

echo ""
echo "Release gate PASSED. Artifacts in: ${DIST_DIR}"
