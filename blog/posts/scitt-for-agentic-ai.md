---
title: SCITT for Agentic AI
date: June 22, 2026
description: How IETF SCITT transparency receipts work for AI agent evidence.
excerpt: COSE Sign1 statements, Merkle proofs, and transparency receipts for AI.
---

# SCITT for Agentic AI: Transparency Receipts for Autonomous Systems

The IETF SCITT framework was designed to prove that a software artifact existed, was produced by a known identity, and has not been tampered with. This maps directly onto proving what an AI agent did after the fact.

## Core Concepts

SCITT defines three concepts:

- **Statement.** A COSE Sign1 envelope with a payload and signature. Says: "This content existed, signed by this key."
- **Transparency Service.** An append-only log that assigns each statement a sequence number.
- **Receipt.** A signed proof of log inclusion with a Merkle proof for independent verification.

## Mapping to AI Evidence

An AI agent execution produces a sequence of events. Each event can be wrapped in a COSE Sign1 statement. The hash is anchored in a transparency log. The log returns a receipt proving inclusion at a specific time.

The result: proof that an AI decision existed at a specific time, signed by a known key, independently verifiable without trusting the log operator.

## Practical Implementation

EPI implements a local SCITT transparency service using a SQLite-backed append-only log. When an `.epi` artifact is produced, the manifest is wrapped in COSE Sign1, registered in the log, and the receipt is embedded in the artifact.

Verification is two-phase:
1. Integrity and signature checks
2. SCITT receipt verification using the Merkle inclusion proof

Receipt verification requires no network access when the service key is known -- the proof is self-contained.

## Why This Matters

SCITT moves an artifact from "this looks valid" to "this was provably produced by a known identity at a known time."
