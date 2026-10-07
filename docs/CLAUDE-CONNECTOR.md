# EPI Evidence Sealer for Claude

Seal a Claude conversation or an agent run into a signed, tamper-evident `.epi` file. You get a link that opens the record in a browser, a download link and a SHA-256. Anyone can check the file later without an account.

- Connector address: `https://epi-mcp.onrender.com/mcp`
- Operator: EPI Labs, https://epilabs.org
- Support: https://epi-mcp.onrender.com/support
- Privacy: https://epi-mcp.onrender.com/privacy
- Terms: https://epi-mcp.onrender.com/terms
- Open source: https://github.com/mohdibrahimaiml/epi-recorder

## What it does

The connector adds one action that changes anything and three read-only checks.

| Tool | What it does | Changes anything? |
| --- | --- | --- |
| `epi_seal_record` | Builds a signed `.epi` file from the messages and tool calls Claude sends, and returns view and download links, the SHA-256, a self-check and warnings. | Creates one new file on the server and asks a public service for a trusted time stamp (see Data handling). It deletes nothing. |
| `epi_verify` | Checks a sealed file: integrity, signature and signer status. | No |
| `epi_export_summary` | Reads a sealed file's timeline back. | No |
| `epi_compare_runs` | Compares two sealed files: step differences and the first point where they diverge. | No |

Two ready-made prompts appear in Claude's menu: **Seal this conversation** and **Seal your last answer**.

## Connect

1. In Claude, open **Settings → Connectors** and add a custom connector with the address above (or add it from the connector directory once listed).
2. Claude opens an approval page. Approve it. Signing in with GitHub is optional. Without it you get a private pseudonymous signer; with it, the sealed file records that the server saw you sign in as your GitHub account.
3. Switch the connector on for the chat you want to seal.

## Use

Say it the way you would to a colleague:

- "Seal this chat with the EPI Evidence Sealer."
- "Seal only your last answer."
- "Verify the file you just sealed."

Claude sends the conversation to the connector and replies with:

- a **view link** that opens the sealed record in any browser,
- a **download link** to keep the file (it expires, see below),
- the **SHA-256** of the file,
- **warnings** about anything missing, such as messages with no timestamps or content that was summarised rather than quoted.

## Check a sealed file

- Upload it at https://epilabs.org/verify. No account is needed.
- Or run `pip install epi-recorder` then `epi verify record.epi`.
- To treat your signer as known, run `epi keys trust record.epi --name <label>`.

Editing any byte of the file makes verification fail.

## What a seal does and does not show

A seal shows the record has not changed since it was sealed. It does **not** show that:

- the record is complete, or that Claude captured everything,
- a message really came from a particular person or AI product,
- the person who signed in typed the conversation.

Claude and ChatGPT do not tell the connector who the user is. The optional sign-in name is asserted by the sealing server, not by Claude. Each result lists what was not captured. Every event the chat does not time-stamp gets the server's receive time and a warning.

## Data handling

- The connector receives only what Claude sends when you ask it to seal, plus the optional sign-in details above.
- Sealed files are **deleted from the server 24 hours after sealing**. Download yours.
- View and download links contain a secret and stop working at expiry. Treat them like the conversation itself.
- To add a trusted time, only a hash of the file's step list (not the content) is sent to the public timestamp service FreeTSA.
- Content is not sold, used for advertising or used to train models.
- Passwords, keys and other people's personal data are best left out or shown as `[REDACTED]`.

Full text: https://epi-mcp.onrender.com/privacy

## Limits

- Each connected account has a cap on live files and total size, and the public `/seal` page limits how often one connection can seal.
- Very long chats can be slow or too large for one call. Use "Seal your last answer", or upload a chat export at https://epi-mcp.onrender.com/seal (no model involved).

## Troubleshooting

| What you see | What to do |
| --- | --- |
| The first request after a quiet period is slow | The service runs on free hosting and sleeps when idle. Open https://epi-mcp.onrender.com/support, wait up to a minute, then retry. |
| "Session expired" | Reconnect the connector or start a new chat. |
| Claude says sealing failed | Nothing was sealed. Retry, or use "Seal your last answer". |
| The view link says it is expired or not valid | Use the exact link Claude returned, including everything after `?t=`. After 24 hours files are removed; upload the file you downloaded at https://epilabs.org/verify. |
| Claude wrote a Markdown file instead | A Markdown or text file is not a signed record. Ask again: "Seal this chat with the EPI Evidence Sealer." |

## Support

https://epi-mcp.onrender.com/support. Please include the artifact id shown when the file was sealed and what you saw.
