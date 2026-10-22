# Gateway API surface (machine-readable)

`openapi.gateway.json` is **generated from the running code**, not hand-written:

```bash
python -c "import json; from epi_gateway.main import app; json.dump(app.openapi(), open('docs/api/openapi.gateway.json','w'), indent=2)"
```

Regenerate it whenever gateway routes change; do not hand-edit. The EPI Cloud
Worker API (TypeScript) has no generated spec yet — its protocol is documented
in prose ([WITNESS](../WITNESS.md), [STORAGE](../STORAGE.md),
[internal/cloud-ops.md](../../internal/cloud-ops.md)).

Known spec wart (code, not doc): `record_approval_decision` registers both GET
and POST on `/api/approve/{workflow_id}/{approval_id}`, producing duplicate
operation IDs (FastAPI warning at import). Harmless to serve, annoying to
generated clients — fix in code, then regenerate this file.
