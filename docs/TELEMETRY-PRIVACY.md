# EPI Telemetry Privacy

Telemetry in EPI Recorder is opt-in.

It exists to answer product questions such as which integrations are being used, whether verification is working in CI, and whether teams want pilot/dashboard support. It is not import tracking, user tracking by default, or content collection.

## Default Behavior

By default:

- telemetry is off
- no network calls are made
- no install ID is created
- importing EPI packages does not send anything
- running normal capture/verify commands does not send anything

Check local status with:

```bash
epi telemetry status
```

Enable or disable it with:

```bash
epi telemetry enable
epi telemetry disable
```

## What Telemetry May Send

After opt-in, EPI sends only non-content metrics:

- event name
- timestamp
- EPI version
- Python version
- operating system family
- environment bucket such as `local`, `ci`, `github_actions`, `docker`, or `aws_lambda`
- integration type
- command name
- success/failure
- artifact bytes
- artifact count
- CI flag

## What Telemetry Never Sends

EPI telemetry must not send:

- prompts
- model outputs
- file paths
- repo names
- hostnames
- usernames
- API keys
- tokens or secrets
- artifact content
- customer data

If telemetry input includes banned field names, the client drops the event and the gateway rejects the payload.

## Pilot Signup

The EPI Pilot signup is separate from anonymous telemetry. It is used for people who explicitly want early access to dashboard/support work.

```bash
epi telemetry enable --join-pilot --email you@example.com --use-case governance --consent-to-contact
```

Pilot signup asks for:

- email
- organization
- role
- use case: `debugging`, `governance`, `compliance`, `agt integration`, `ci/cd`, or `other`
- consent to contact
- optional consent to link telemetry to the pilot profile

Usage-linked outreach is allowed only when the user explicitly passes `--link-telemetry` or answers yes to the equivalent prompt.

## Local Storage

EPI stores local telemetry consent under `~/.epi/` by default:

- `telemetry.json`
- `pilot_signup.json`

Set `EPI_HOME` to use a different local state directory.

## Gateway Ingestion

Self-hosted gateways reject telemetry by default. Enable ingestion only when you intentionally operate a telemetry endpoint:

```bash
EPI_GATEWAY_TELEMETRY_ENABLED=true epi gateway serve
```

Enabled gateways accept:

- `POST /api/telemetry/events`
- `POST /api/telemetry/pilot-signups`

Records are appended under the gateway storage directory. Pilot signup records are stored separately from anonymous telemetry events.
