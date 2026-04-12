# EPI Self-Hosted Reliability Runbook

This runbook defines the supported `v4.0.0` self-hosted shape for EPI:

- single-node deployment
- append-only event spool on disk
- SQLite shared case store
- shared reviewer workflow in the browser
- portable `.epi` export from any shared case

## Supported Shape

- Gateway: `epi gateway serve` or the `gateway` Docker service
- Viewer: `epi connect open` locally, or the `viewer` Docker service
- Storage root:
  - event spool: `events/`
  - SQLite: `cases.sqlite3`
- Providers with the strongest support:
  - OpenAI-compatible proxy: `/v1/chat/completions`
  - Anthropic-compatible proxy: `/v1/messages`

## Defaults

- retention mode: `redacted_hashes`
- proxy failure mode: `fail-open`
- capture scope: `consequential`
- auth: optional shared bearer token or local users file for `/api/*`

## Fast Start

1. Copy [.env.example](/C:/Users/dell/epi-recorder/.env.example) to `.env`.
2. Choose one of these if you want the shared reviewer workspace protected:
   - set `EPI_GATEWAY_ACCESS_TOKEN` for one shared bearer token
   - or set `EPI_GATEWAY_USERS_FILE` to a local users JSON file like [config/gateway-users.example.json](/C:/Users/dell/epi-recorder/config/gateway-users.example.json)
3. Start the supported stack:

```bash
docker compose up --build
```

4. Open the viewer:

```text
http://127.0.0.1:8000/web_viewer/index.html
```

5. Health and readiness:

```text
http://127.0.0.1:8765/health
http://127.0.0.1:8765/ready
```

## Meaning of Health vs Ready

- `/health`: process is alive and can report runtime configuration/state
- `/ready`: replay finished and the shared case store is ready to serve traffic

`/ready` may return `ready-with-warnings` when startup succeeded but corrupt replay batches or projection failures were detected. In that case:

- review the replay fields in the response
- inspect `events/corrupt/`
- decide whether to repair or re-ingest the affected batches

## Storage Layout

Example storage root:

```text
.epi-data/
  cases.sqlite3
  events/
    evidence_batch_x.json
    corrupt/
      evidence_bad.json.corrupt
```

The append-only spool is the recovery source of truth. SQLite is the live shared reviewer database.

## Backup

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup-gateway.ps1 -StorageDir .\.epi-data
```

Optional key backup:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup-gateway.ps1 -StorageDir .\.epi-data -KeysDir .\keys
```

Back up:

- storage root (`events/` + a `cases.sqlite3` snapshot)
- signing keys
- `.env`

The backup script now snapshots `cases.sqlite3` with SQLite's backup API before
archiving it, so reviewer workflow state and comments are preserved alongside
the append-only spool.

## Restore

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restore-gateway.ps1 -BackupFile .\backups\epi-gateway-backup-YYYYMMDD-HHMMSS.zip -RestoreDir .
```

After restore:

1. verify `.env`
2. start the stack
3. check `/ready`
4. verify a known case can be opened and exported

## Operator Drill

Run the supported single-node drill end to end:

```powershell
.venv-release\Scripts\python.exe scripts\self_hosted_drill.py
```

The drill validates:

- gateway startup and `/ready`
- viewer availability
- shared case capture
- assignment, due date, comment, and review persistence
- `.epi` export and `epi verify`
- backup and restore into a fresh storage root

## Upgrade Policy

- keep the existing storage root before upgrading
- take a full backup first
- upgrade the package/container
- start the gateway and wait for `/ready`
- if new replay warnings appear, inspect `events/corrupt/`

## Operator Checklist

- `/ready` returns `ready` or `ready-with-warnings`
- `corrupt_batch_count` is understood and tracked
- `projection.failure_count` is understood and tracked
- the shared inbox loads in the browser
- review save works
- `.epi` export works
- exported artifact passes `epi verify`

## Troubleshooting

### Shared inbox not loading

- check `/health`
- check `/ready`
- if auth uses a shared token, enter it in the viewer advanced connection settings
- if auth uses local users, sign in from the browser app's shared sign-in panel

### Cases missing after restart

- inspect `events/`
- inspect `events/corrupt/`
- compare `replayed_batches` and `corrupt_batch_count` from `/health` and `/ready`

### Export fails

- confirm the case still loads from `/api/cases/{id}`
- inspect gateway logs for the case ID
- verify the storage path has write access for temporary export files

### Need portable proof for audit

Use either:

```bash
epi gateway export --case-id <CASE_ID> --out exported.epi --storage-dir ./.epi-data
```

or:

- open the case in the shared browser UI
- export the reviewed `.epi`
