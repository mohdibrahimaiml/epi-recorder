# Identity onboarding (did:web)

A fresh key verifies as NOT_PINNED, and anyone can re-sign a rebuilt chain
with a fresh key. This page binds the vendor's key to the vendor's domain
once, for free.

## For the vendor (5 minutes)

1. If you have no key yet: `epi keys generate`.
2. Publish your key:
   `epi keys did --domain vendor.com [--path agents/claims] [--key default]`
   This writes `did.json` and prints the DID (`did:web:vendor.com`, or
   `did:web:vendor.com:agents:claims` with `--path`) and the exact URL to
   host it at (`https://vendor.com/.well-known/did.json`, or
   `https://vendor.com/agents/claims/did.json`).
3. Upload `did.json` to that URL with any static host (GitHub Pages and
   Cloudflare Pages both work; no server code needed).
4. Seal with the DID attached: `record(..., did="did:web:vendor.com")`
   (or set `EPI_DID`; the gateway uses its `did_web` setting). The DID lands
   in `manifest.governance["did"]` before signing.
5. Rotating keys: add the new key as another `verificationMethod` entry in
   `did.json` (keep the old one until customers have pinned the new one).
   Verifiers accept any listed Ed25519 key.

## For the customer (2 minutes)

1. Resolve once and pin: `epi keys trust --from-did did:web:vendor.com --name vendor`.
   It prints the key fingerprint — confirm it with the vendor out of band
   (call, contract, existing secure channel). For rotation, pin each key in
   their `did.json`.
2. Verify: `epi verify run.epi`.
   - Pinned key: identity KNOWN.
   - No pins at all: soft `NOT_PINNED` (normal for a first look).
   - Pins exist but the file's key is not among them: red
     `NOT A KEY YOU TRUST (you have pinned: vendor). This file was not
     sealed by a key you trust.`
   - Add `--offline` to skip all network (DID shows as declared but
     unresolved; local pins still decide).

## What this does not do

- It does not prove the vendor recorded everything, told the truth, or
  complied with anything — only that the sealing key is the one the domain
  publishes (or was, at pin time).
- If the vendor's web server is compromised, the attacker can publish a new
  key. Pins you already made do not change; re-confirm out of band before
  trusting a new key.
