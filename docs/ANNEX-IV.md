# Annex IV templates (`epi annex`)

**Product version:** 4.6.2.  
**Not a certificate. Not a legal Declaration of Conformity.**

`epi annex` helps you **author, validate, sign, and pack** nine JSON files whose *shape* follows EU AI Act Annex IV section headings. You supply the facts. EPI hashes and can sign the bytes you wrote.

A completed tree of JSON files, even when packed into a `.epi`, does **not** mean the AI system is EU AI Act conformant. Counsel and your notified body (if any) decide that.

Related: [EU-AI-ACT-EVIDENCE-PREP.md](./EU-AI-ACT-EVIDENCE-PREP.md), [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md).

## What the CLI does

```
epi annex init              # write nine section JSON templates
epi annex validate          # schema-check the JSON
epi annex sign 1            # Ed25519-sign section 1
epi annex sign all
epi annex verify all        # verify those signatures
epi annex status            # per-section completion of the templates
epi annex compile           # write compliance-summary.json from the templates
epi annex report            # HTML report of the same JSON
```

Schemas live in `epi_core.annex_schemas` and `docs/spec/schemas/annex-iv.schema.json`.

## The nine section files

| Sec | Heading in the template | What you still owe |
|-----|-------------------------|--------------------|
| 1 | System description | Intended purpose, version, provider — in your words |
| 2 | Development process | Architecture, data, testing, cybersecurity as they actually are |
| 3 | Monitoring and control | Capabilities, limitations, subgroup metrics you measured |
| 4 | Performance metrics | Why those metrics, with your numbers |
| 5 | Risk management | Your risk register (the schema can compute RPN from values you enter) |
| 6 | Lifecycle changes | Your change log |
| 7 | Applied standards | Standards you actually applied, including gaps |
| 8 | EU declaration of conformity | A **template** for a legal statement. Signing the JSON is not filing a DoC |
| 9 | Post-market monitoring | Your monitoring and incident plan |

## Signing

Each section file can be signed with Ed25519. Keys default to `~/.epi/keys/`. Example:

```
epi annex sign 1 --key-name compliance-officer --officer did:web:example.com
epi annex verify 1
```

That signature proves **those JSON bytes** were signed by that key. It does not prove the JSON is complete or true.

## Packing into a `.epi`

Files under `artifacts/annex_iv/` can be packed with the rest of a recording. They are then hashed in `file_manifest` like any other member. Tampering with them after seal fails `epi verify` integrity. That is integrity of **your documentation files**, not regulatory approval.

## Commands

| Command | Description |
|---------|-------------|
| init | Generate template JSON files for all 9 sections |
| validate | Validate JSON against schemas |
| status | Show per-section template completion |
| compile | Generate `compliance-summary.json` from templates |
| sign | Ed25519-sign a section (or `all`) |
| verify | Verify those signatures |
| report | HTML view of the templates |
| pack | Generate all sections, sign, and pack into a signed `.epi` (`--out`, `--key-name`, `--force`; honors `EPI_SIGNING_KEY`) |
| multi-sign | Append a multi-signer approval to the compliance summary (`signer`, `--key-name`, section scope; RBAC-enforced) |
| role-bind / role-unbind / role-list / role-verify | Bind public keys to org roles, list them, verify all signers are authorized (`--strict` to require it) |
