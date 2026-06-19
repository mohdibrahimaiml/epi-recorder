# EPI Telemetry Privacy

Telemetry in EPI Recorder is opt-in.

It exists to answer product questions such as which integrations are being used, whether verification is working in CI, and whether teams want pilot/dashboard support. It is not import tracking, user tracking by default, or content collection.

## Default Behavior

By default:

- telemetry is off
- no network calls are made
- an anonymous install ID is created locally on the first CLI run so events can be attributed after you opt in
- importing EPI packages does not send anything
- running normal capture/verify commands does not send anything
- local opt-in reminders after high-intent commands do not send anything

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

The EPI Pilot signup is separate from anonymous telemetry. It is used for people who explicitly want early access to artifact dashboard, compliance report exports, priority support, and roadmap input.

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
- `telemetry_queue.jsonl`

Set `EPI_HOME` to use a different local state directory.

`telemetry_queue.jsonl` is created only after telemetry opt-in when a sanitized event cannot be delivered. Later telemetry sends retry queued events. Repeatedly failing queued events are dropped after a small number of attempts.

## Gateway Ingestion

Self-hosted gateways reject telemetry by default. Enable ingestion only when you intentionally operate a telemetry endpoint:

```bash
EPI_GATEWAY_TELEMETRY_ENABLED=true epi gateway serve
```

Enabled gateways accept:

- `POST /api/telemetry/events`
- `POST /api/telemetry/pilot-signups`

Records are appended under the gateway storage directory. Pilot signup records are stored separately from anonymous telemetry events.


## Organization Discovery

When telemetry is enabled, EPI may derive non-identifying organization signals from your local git config:

- `email_domain`: extracted from `git config user.email` (e.g., `microsoft.com`). The full email address is never sent.
- `github_org`: extracted from `git remote -v` for `github.com` remotes (e.g., `openai`). The repository name is never sent.

These signals are only collected if git is available and the working directory is inside a git repository. They help EPI Labs understand which organizations are finding value in EPI, without identifying individual users.

## Optional Account System

`epi login` is entirely optional and only required for cloud-only features such as registry, cloud sync, team collaboration, and enterprise features. When you log in:

- EPI opens a browser-based GitHub OAuth flow.
- A bearer token is stored locally in `~/.epi/auth.json`.
- Telemetry events may include `user_id` and `org_id` so usage can be linked to your account.

You can log out at any time with `epi logout`.

Core local commands (`epi record`, `epi verify`, `epi view`, `epi demo`) never require an account.
