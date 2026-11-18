# Gateway API surface (machine-readable)

`openapi.gateway.json` is **generated from the running code**, not hand-written.
The gateway ships in the paid `epi-enterprise` package, not in this repository:

```bash
pip install epi-enterprise   # from the private index, with a licence
python -c "import json; from epi_enterprise.gateway.main import app; json.dump(app.openapi(), open('docs/api/openapi.gateway.json','w'), indent=2)"
```

Regenerate it whenever gateway routes change; do not hand-edit. The EPI Cloud
Worker API (TypeScript) has no generated spec yet — its protocol is documented
in prose ([WITNESS](../WITNESS.md), [STORAGE](../STORAGE.md)). The founder-ops
runbook is internal and is not linked from here.

The approval link is two operations: `GET` renders the confirmation page and
records nothing, `POST` records one link click (single-use token in the form
body). See [HUMAN-APPROVAL.md](../HUMAN-APPROVAL.md).
