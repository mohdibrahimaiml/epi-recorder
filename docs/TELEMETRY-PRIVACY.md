# EPI Telemetry Privacy

**Product version:** 4.6.2. **4.6.3 (release pending).**

Telemetry in EPI Recorder is opt-in.

It exists to answer product questions such as which integrations are being used, whether verification is working in CI, and whether teams want pilot/dashboard support. It is not import tracking, user tracking by default, or content collection.

## Default Behavior

By default:

- telemetry is off
- no network calls are made
- a random install ID is created locally only after you opt in (`epi telemetry enable` or the first post-opt-in event), so pre-opt-in runs create no identifier; it is not linked to your identity unless you explicitly join the pilot
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
- organization-level git signals: `email_domain`, `github_org` (see below; can be omitted with `EPI_TELEMETRY_ORG_SIGNALS=0`)

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

The EPI Pilot signup is separate from telemetry events. It is used for people who explicitly want early access to artifact dashboard, compliance report exports, priority support, and roadmap input.

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

Records are appended under the gateway storage directory. Pilot signup records are stored separately from telemetry events.


## Organization-level signals (on by default when telemetry is on)

**4.6.3 (release pending):** the `EPI_TELEMETRY_ORG_SIGNALS=0` opt-out ships in 4.6.3. In 4.6.2, organization signals are attached when telemetry is on and there is no opt-out.

When telemetry is enabled, EPI **automatically** attaches organization-level
signals derived from your local git config to each telemetry event:

- `email_domain`: extracted from `git config user.email` (e.g., `microsoft.com`). The full email address is never sent.
- `github_org`: extracted from `git remote -v` for `github.com` remotes (e.g., `openai`). The repository name is never sent.

These are organization-level, **not anonymous** — an employer domain or GitHub
org can identify a small team. They are collected only if git is available and
the working directory is inside a git repository. They help EPI Labs understand
which organizations are finding value in EPI.

To omit them while keeping telemetry on, set:

```bash
export EPI_TELEMETRY_ORG_SIGNALS=0
```

Disabling telemetry (`epi telemetry disable`) stops all events, including these
signals. Nothing is derived or sent before telemetry is opted in.

## Optional Account System

`epi cloud login` is entirely optional and only required for cloud-only features such as registry, cloud sync, team collaboration, and enterprise features. When you log in:

- EPI uses the EPI Cloud device flow (RFC 8628): the terminal shows a short code you type at `cloud.epilabs.org/auth/device`. `epi auth login` is an alias of the same flow.
- A push-only key for EPI Cloud is stored locally in `~/.epi/cloud.json` (mode 0600). (`~/.epi/auth.json` is a leftover local-dev token file, not the Cloud login.)
- Telemetry events may include `user_id` and `org_id` so usage can be linked to your account.

You can log out at any time with `epi auth logout` (clears `cloud.json`). There is no `epi login` / `epi logout` command.

Core local commands (`epi record`, `epi verify`, `epi view`, `epi demo`) never require an account.
