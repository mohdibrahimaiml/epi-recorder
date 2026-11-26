# Running the EPI MCP server in Docker

The image in the repository root (`Dockerfile`) runs the **stdio** MCP server,
entrypoint `epi-mcp` (`epi_mcp.server:main`). It needs no arguments, no API key
and no network access to start: `initialize`, `tools/list` and `prompts/list`
are answered offline. That is what directory crawlers such as Glama use to
inspect the server.

## Build

```bash
docker build -t epi-recorder-mcp .
```

The build installs the project from source with `pip install ".[mcp]"` — the
`[mcp]` extra is the MCP SDK the server imports; dev and test extras are not
installed. The image is built in two stages, so only the virtualenv (not the
source tree or a compiler) ends up in the final layer. It runs as the
non-root user `app` (uid 10001).

## Run

MCP over stdio reads JSON-RPC from stdin and writes it to stdout, so the
container must be started with `-i` (and **not** `-t`, which corrupts the
stream with a TTY):

```bash
docker run -i --rm epi-recorder-mcp
```

A one-shot check that the server is alive:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0.0.0"}}}' \
  | docker run -i --rm epi-recorder-mcp
```

The reply names the server `epi-evidence` and lists the tools `epi_seal_record`,
`epi_verify`, `epi_export_summary`, `epi_compare_runs` and
`epi_delete_artifact`.

## Point an MCP client at it

Any client that can launch a stdio command works. For a client configured with
JSON (Claude Desktop, Cursor, and most others):

```json
{
  "mcpServers": {
    "epi-evidence": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "epi-recorder-mcp"]
    }
  }
}
```

To keep sealed artifacts and the signing key across container runs, add a
volume for the keys directory:

```json
{
  "mcpServers": {
    "epi-evidence": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "epi-mcp-keys:/home/app/.epi/keys",
        "epi-recorder-mcp"
      ]
    }
  }
}
```

## Environment variables

None are required. The ones that change behaviour for a local stdio container:

| Variable | Default in the image | Effect |
| --- | --- | --- |
| `EPI_MCP_KEYS_DIR` | `/home/app/.epi/keys` | Where the server's Ed25519 signing key is stored. Created on first seal; mount a volume here to keep the same signer across runs. |
| `EPI_SIGNING_SEED` | unset | Optional 32+ character server seed. When set, per-caller signing keys are derived from it instead of being generated and stored, so signers stay stable even if the container filesystem is reset. Guard it like a root key. |
| `EPI_NOTARIZE` | `1` (on) | On seal, a hash is sent to a public RFC 3161 time-stamp service (no content leaves the server). Set to `0` for a fully offline container; seals then carry no trusted timestamp. |
| `EPI_TSA_TIMEOUT` | `6` | Seconds to wait for the time-stamp service before sealing without a token. |

`EPI_MCP_TOKEN`, `EPI_OAUTH_SECRET`, `EPI_OIDC_*` and `EPI_IDP_*` are for the
hosted HTTP transport (`epi-mcp-http`); the stdio server ignores them apart from
`EPI_OAUTH_SECRET`/`EPI_SIGNING_SEED` as a key seed.

## Scope and limitations

- This image is **stdio only**. The Streamable HTTP server (`epi-mcp-http`,
  endpoint `/mcp`) is a separate entry point that requires a bearer token
  (`EPI_MCP_TOKEN`) and a public hostname; it is not what this container runs.
- One client per container. stdio is a single-connection transport; run one
  container per client.
- Sealing writes the key to `EPI_MCP_KEYS_DIR` and the sealed file to a
  temporary directory inside the container. Without a mounted volume both are
  lost when the container is removed — the tool returns the file bytes, the
  SHA-256 and the links, so the record itself is not lost.
