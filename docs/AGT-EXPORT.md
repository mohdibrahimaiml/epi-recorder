AGT Export
==========

This document shows how to export a sealed `.epi` artifact into a normalized
AGT-style audit JSON bundle using the `epi` CLI.

Why export?
-----------

- Produce a governance-friendly audit record derived from a sealed EPI artifact.
- Keep `policy_evaluation` and `steps` evidence together while emitting a
  normalized, consumable JSON for governance tooling.

CLI: `epi export agt`
---------------------

Examples:

Export a case file to AGT JSON (defaults to `*.agt.json`):

```bash
epi export agt my_case.epi
```

Export with explicit output filename and include raw manifest/steps:

```bash
epi export agt my_case.epi --out my_case.agt.json --include-raw
```

Identity mapping
----------------

Register a local agent name to a DID so the exporter can populate `agent.id`:

```bash
epi identity register claims-agent did:key:z6Mkw... --public-key ed25519:...
```

Export current identity mapping to a JSON file:

```bash
epi identity export identity_map.json
```

Import an identity mapping produced by another team:

```bash
epi identity import org_identity_map.json
```

Notes
-----

- The `epi` exporter does not modify the sealed `.epi` artifact. It reads the
  artifact contents, normalizes events into an AGT-like shape, and writes a
  separate JSON bundle.
- The export is intentionally additive and optional; existing `.epi` readers
  are not affected.
