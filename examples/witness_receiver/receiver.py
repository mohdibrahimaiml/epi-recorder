"""Reference customer witness receiver (kept for reference).

The receiver now ships with the package -- prefer the installed command:

    epi witness serve --port 8099 --secret SHARED_SECRET --out received.jsonl

This script is a thin wrapper around ``epi_core.witness_receiver`` with the
same flags as before:

    python receiver.py --port 8099 --secret SHARED_SECRET --out received.jsonl

It verifies the HMAC, stamps `received_at`, and appends each payload to
`received.jsonl` -- the file the customer later checks with:

    epi verify run.epi --witness-log received.jsonl

The default host is 127.0.0.1 (this machine only). For a vendor on another
machine, listen on 0.0.0.0 behind a TLS-terminating reverse proxy (Caddy,
nginx, a cloud load balancer) and give the vendor the https:// URL. The
secret can also come from the EPI_WITNESS_SECRET environment variable.
Unlike `epi witness serve`, this script runs without a secret (HMAC check
off) when none is given.
"""

from __future__ import annotations

import sys

from epi_core.witness_receiver import build_parser, main

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    sys.exit(main())
