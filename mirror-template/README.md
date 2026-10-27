# EPI witness checkpoints (public mirror)

This repository is a **write-once mirror** of the signed checkpoints published by
the EPI witness at `https://cloud.epilabs.org`. It exists so that the witness's
history is visible in a second place that EPI Labs cannot silently rewrite.

- `checkpoints/<inbox>.json` — one file per customer inbox. The document is
  **append-only**: a day that already exists never changes. If the live witness
  ever serves a different `count` / `head_hash` / `signature` for a day that is
  already here, the mirroring job fails loudly and nothing is committed.
- `witness-key.json` — the witness's Ed25519 public key, copied from
  `https://cloud.epilabs.org/.well-known/epi-witness-key.json`.

This repository contains **no customer evidence**. Checkpoints are hashes: an
inbox id, a day, a count, a head hash and a signature. No prompts, no file
contents, no personal data.

## Verify a checkpoint by hand

Nothing here needs EPI to check. A checkpoint is valid when its Ed25519
signature verifies over the canonical JSON of four fields.

```bash
# 1. Take one line out of a checkpoints file
python - <<'PY'
import json
doc = json.load(open("checkpoints/inb_example.json"))
cp = doc["checkpoints"][-1]
print(cp["day"], cp["count"], cp["head_hash"])
print(cp["signature"])
PY
```

```bash
# 2. Rebuild the signed message and verify it with the published key
python - <<'PY'
import json, binascii
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

doc = json.load(open("checkpoints/inb_example.json"))
keys = json.load(open("witness-key.json"))
cp = doc["checkpoints"][-1]
msg = json.dumps(
    {"inbox": doc["inbox"], "day": cp["day"], "count": cp["count"], "head_hash": cp["head_hash"]},
    separators=(",", ":"),
).encode()
pub = Ed25519PublicKey.from_public_bytes(binascii.unhexlify(keys["witness_ed25519_pub_hex"]))
pub.verify(binascii.unhexlify(cp["signature"]), msg)   # raises if invalid
print("signature valid")
PY
```

The same check is built in, and also compares the mirror against the live
witness:

```bash
epi witness check --inbox-url https://cloud.epilabs.org/w/inb_example \
  --mirror https://raw.githubusercontent.com/<owner>/epi-witness-checkpoints/main
```

It fails if a mirrored day is missing or changed on the live side (history
rewritten), or if the witness key changed without a key-rotation entry.

## Reporting a mismatch

If a day in this repository disagrees with the live witness, or a commit here
changed an existing day, that is a security report — **not** a normal issue.
Use GitHub private vulnerability reporting on
[`mohdibrahimaiml/epi-recorder`](https://github.com/mohdibrahimaiml/epi-recorder/security/advisories/new)
so it is handled privately first. See `SECURITY.md` there.

## How this repository is updated

`epi-recorder`'s `witness-mirror` GitHub Action runs daily, verifies every
checkpoint signature, refuses any change to an existing day, cross-checks the
result against the live witness, and only then pushes. The commit author is a
machine account; a human never edits these files.
