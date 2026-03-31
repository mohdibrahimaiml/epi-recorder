# Share With Your Team Locally

`epi connect open` is the local team-review path. It starts the EPI gateway and the browser workspace together so another reviewer can inspect cases without piecing together ports and HTML files by hand.

## What `epi connect open` starts

Today the command starts two local services:

- gateway on `http://127.0.0.1:8765`
- browser workspace on `http://127.0.0.1:8000/web_viewer/index.html`

Fast path:

```bash
epi connect open
```

Useful variants:

```bash
epi connect open --no-browser
epi connect open --host 0.0.0.0
epi connect open --users-file ./config/gateway-users.example.json
```

When the browser opens, it includes the `bridgeUrl` query parameter so the workspace knows which local gateway to talk to.

## Same-machine review

If the reviewer is on the same machine:

1. run `epi connect open`
2. let the browser open automatically
3. hand the reviewer the opened URL or sit together in the browser workspace

This is the easiest path for demos, local triage, and internal pair debugging.

## Share on your LAN

To let another machine on the same network open the workspace:

```bash
epi connect open --host 0.0.0.0
```

Then share a URL shaped like this, replacing `192.168.1.50` with your machine's LAN IP:

```text
http://192.168.1.50:8000/web_viewer/index.html?bridgeUrl=http%3A%2F%2F192.168.1.50%3A8765
```

Why the full URL matters:

- the viewer lives on port `8000`
- the browser app still needs to know the gateway address on `8765`
- the `bridgeUrl=...` query parameter preloads the correct gateway address for the reviewer

If you share only `http://192.168.1.50:8000`, the reviewer may need to enter the gateway address manually in Setup.

## Temporary remote review with ngrok

If you need a short-lived remote demo, tunnel both services and share the workspace URL:

```bash
ngrok http 8000
ngrok http 8765
```

Then build a shared URL like:

```text
https://YOUR-WEB-TUNNEL.ngrok-free.app/web_viewer/index.html?bridgeUrl=https%3A%2F%2FYOUR-GATEWAY-TUNNEL.ngrok-free.app
```

Use this for temporary demos only. For longer-lived sharing, move to hosted sharing in a later phase.

## Connector setup paths available today

The local workspace can fetch one live source record through the connector bridge. Current connector paths in `epi connect` include:

- Zendesk
- Salesforce
- ServiceNow
- internal app / generic HTTP
- CSV export

Typical setup flow in the browser:

1. open Setup
2. choose the source system
3. enter the bridge URL
4. check bridge health
5. fetch one live record into the starter flow

For protected local setups you can also use:

- `--access-token` for a shared bearer token
- `--users-file` for a simple local sign-in flow

## Reviewer workflow in the browser

Once the workspace is open, the reviewer flow is:

1. open the inbox or selected case
2. inspect the case summary and timeline
3. review rules, guidance, and trust state
4. add review notes
5. export the reviewed case file

This is the right path when the team wants a shared local workspace instead of trading `.epi` files one by one.

## When to use which path

Use `epi view` when:

- you already have a `.epi` file
- one person just needs to inspect it locally

Use [epilabs.org/verify](https://epilabs.org/verify) when:

- someone only needs a browser trust check
- you do not want them to install anything

Use `epi connect open` when:

- you want a local team review workspace
- a reviewer wants to inspect and comment in the browser
- you need connector-backed record fetching on the same machine or LAN

## Related guides

- [Share one failure with `.epi`](SHARE-A-FAILURE.md)
- [Use `pytest --epi` for agent regressions](PYTEST-AGENT-REGRESSIONS.md)
- [Framework integrations in 5 minutes](FRAMEWORK-INTEGRATIONS-5-MINUTES.md)
