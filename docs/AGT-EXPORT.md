# AGT export (`epi export agt`)

**Product version:** 4.6.3.

Read a sealed `.epi` and write a **separate** AGT-shaped JSON bundle. The original `.epi` is not modified. This is not Microsoft AGT, not a certificate, and not a substitute for [AGT-IMPORT-QUICKSTART.md](./AGT-IMPORT-QUICKSTART.md) (the other direction).

```bash
epi export agt my_case.epi
epi export agt my_case.epi --out my_case.agt.json --include-raw
```

Optional identity mapping so the exporter can fill `agent.id`:

```bash
epi identity register claims-agent did:key:z6Mkw... --public-key ed25519:...
epi identity export identity_map.json
epi identity import org_identity_map.json
```
