"""EPI witness keys pinned in the package (M6 evidence pack).

These are the ONLY keys the verifier trusts besides an explicit
``--witness-pubkey`` flag / ``EPI_WITNESS_PUBKEY`` env. A ``witness_pubkey``
shipped *inside* a pack (``witness.json``) is NEVER trust — it is a hint for
display only. Trusting it would let a forger self-stamp any run (passport
printing its own stamp sample).

Populated once the founder creates ``WITNESS_SIGNING_KEY`` (docs/CLOUD.md
§4): paste the hex from ``/.well-known/epi-witness-key.json`` AND confirm
the identical key in the public ``epi-witness-checkpoints`` GitHub repo.
Both places must agree before a key lands here.
"""

from __future__ import annotations

# Ed25519 public keys (64 lowercase hex chars) the verifier trusts for
# witness receipts. Empty until the production witness key exists.
EPI_WITNESS_PUBKEYS: tuple[str, ...] = ()


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
