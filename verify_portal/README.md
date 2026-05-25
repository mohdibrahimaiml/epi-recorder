# EPI Verify Portal

Web-based verification service for `.epi` artifacts. No installation required.

## Features

- **Drag & drop upload** — verify any `.epi` file in your browser
- **Integrity check** — SHA-256 file manifest verification
- **Signature validation** — Ed25519 signature verification against trust registries
- **AIUC-1 mapping** — Maps evidence to AIUC-1's six trust domains (A-F)
- **Signed attestation** — Download a JSON attestation signed by `did:web:epilabs.org`
- **Rate limiting** — 3 free verifications per IP per day

## Quick Start

```bash
pip install -e ".[gateway]"
python -m verify_portal.main
```

Visit `http://localhost:8000` and upload an `.epi` file.

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install -e ".[gateway]"
EXPOSE 8000
CMD ["python", "-m", "verify_portal.main"]
```

### Cloudflare Workers / Vercel

The frontend (`static/index.html`) is a standalone static page. You can deploy it
to any static host and point the API calls to your backend.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server port |
| `EPI_KEYS_DIR` | `~/.epi/keys` | Directory containing signing keys |

## API

### POST /api/verify

Upload a `.epi` file and receive a verification report.

**Request:**
```bash
curl -X POST -F "file=@artifact.epi" -F "aiuc1=true" http://localhost:8000/verify
```

**Response:**
```json
{
  "facts": {
    "integrity_ok": true,
    "signature_valid": true,
    "sequence_ok": true,
    "completeness_ok": true,
    "chain_ok": true,
    "transparency_ok": true
  },
  "identity": {
    "status": "KNOWN",
    "name": "EPI Labs Official",
    "did": "did:web:epilabs.org"
  },
  "aiuc1": {
    "overall": "PASS",
    "domains": {
      "A": { "label": "Data & Privacy", "status": "PASS" },
      "B": { "label": "Security", "status": "PASS" },
      "C": { "label": "Safety", "status": "PASS" },
      "D": { "label": "Reliability", "status": "PASS" },
      "E": { "label": "Accountability", "status": "PASS" },
      "F": { "label": "Society", "status": "PASS" }
    }
  },
  "attestation": {
    "payload": { ... },
    "signature": "ed25519:epilabs:<hex>",
    "did": "did:web:epilabs.org"
  }
}
```

## Architecture

```
Frontend (static/index.html)
    │
    ▼ POST /api/verify  (multipart/form-data)
Backend (verify_portal/main.py)
    │
    ├── epi_core.container.EPIContainer.verify_integrity()
    ├── epi_core.trust.verify_embedded_manifest_signature()
    ├── epi_core.aiuc1_mapping.map_verification_to_aiuc1()
    └── Sign attestation with Ed25519 key
```
