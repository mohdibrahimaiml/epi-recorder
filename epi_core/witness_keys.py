"""EPI witness keys pinned in the package (M6 evidence pack).

These are the ONLY keys the verifier trusts besides an explicit
``--witness-pubkey`` flag / ``EPI_WITNESS_PUBKEY`` env. A ``witness_pubkey``
shipped *inside* a pack (``witness.json``) is NEVER trust — it is a hint for
display only. Trusting it would let a forger self-stamp any run (passport
printing its own stamp sample).

Populated once the founder creates ``WITNESS_SIGNING_KEY`` (docs/CLOUD.md
§4): paste the hex from ``/.well-known/epi-witness-key.json`` and confirm the
fingerprint through an independent channel (your contract, or a prior signed
checkpoint). A public ``epi-witness-checkpoints`` mirror is planned but not
published as of 2026-10-23; when it exists, cross-check there too.
"""

from __future__ import annotations

# Ed25519 public keys (64 lowercase hex chars) the verifier trusts for
# witness receipts. Empty until the production witness key exists.
EPI_WITNESS_PUBKEYS: tuple[str, ...] = (
    # Production witness key, created 2026-10-16. Confirmed against the live
    # /.well-known/epi-witness-key.json Worker at pin time. The public
    # epi-witness-checkpoints mirror is planned, not yet published, so this pin
    # has not been cross-checked there.
    "6a7dc25154809f8401892ff399a0b9c32ea9c14e5b519ccda3a48508b3e2aa97",
)


def pinned_witness_pubkeys() -> list[str]:
    """Return the package-pinned witness keys, normalised, blanks dropped."""
    out: list[str] = []
    for key in EPI_WITNESS_PUBKEYS:
        text = str(key or "").strip().lower()
        if text.startswith("0x"):
            text = text[2:]
        if text:
            out.append(text)
    return out
