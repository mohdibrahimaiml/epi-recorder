#!/usr/bin/env bash
# The witnessed pilot, end to end. The steps live in run_witness_pilot.py (one
# implementation, cross-platform); this is the shell entry point.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python "$here/run_witness_pilot.py" "$@"
