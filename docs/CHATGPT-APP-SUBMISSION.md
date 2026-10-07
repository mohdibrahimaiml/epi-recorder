# Publish EPI Evidence Sealer in the ChatGPT app directory

Why: a published app is available to ChatGPT users on Free, Go, Plus and Pro (outside the EEA,
Switzerland and the UK, per OpenAI's announcements), so ChatGPT works like the Claude connector
without each user turning on Developer mode or needing a Business plan. Developer mode and custom
connectors are what you use to *test*; the directory is how everyone else gets it.

OpenAI's rules and screens change. This pack was written from public summaries of OpenAI's
guidelines (the official pages could not be opened from the build environment), so read the current
"App submission guidelines" before you submit and adjust anything that has moved.

## What is already done (in this repo)

| Requirement | Where |
|---|---|
| MCP server over HTTPS with OAuth (PKCE, dynamic registration, refresh) | `epi_mcp/http.py`, tested by `tests/test_mcp_chatgpt_flow.py` |
| Accurate tool hints: sealing is a non-destructive write; verify, read back, compare are read-only | `epi_mcp/server.py` |
| Published privacy policy, terms and support pages | `/privacy`, `/terms`, `/support` on the server (`epi_mcp/legal.py`) |
| Retention promise is enforced (files deleted after 24 h by a timer) | `epi_mcp/http.py` purge thread |
| Limits that stop abuse (size, rate, storage) | `epi_mcp/tools.py`, `/seal` |

## What only you can do

1. **Set the contact on the server.** In Render set `EPI_SUPPORT_EMAIL` (a monitored address) and,
   if different from "EPI Labs", `EPI_OPERATOR_NAME`. Redeploy.
2. **Have the privacy policy and terms reviewed by a lawyer.** They describe the server's actual
   behaviour, but they are not legal advice. Confirm the promise "we do not use content to train
   models" is true for your company before you publish it.
3. **Verify your OpenAI platform account** (the submission requires a verified organisation).
4. **Prepare the directory assets:** an icon (square, the EPI logo), 2-4 screenshots of a seal result
   and the view page, and a one-line and a long description (below).
5. **Submit** at platform.openai.com (Apps → Submit). Keep the Case ID you are emailed.

## Directory text (paste and adjust)

**Name:** EPI Evidence Sealer

**One line:** Turn a conversation or AI run into a signed, tamper-evident audit record you can keep and verify.

**Description:** EPI Evidence Sealer creates a signed audit record (.epi file) of a conversation or
workflow when you ask for one, for example "seal this chat". You get a link to view it in your browser,
a download link and a SHA-256. Anyone can later check that the record has not changed, without installing
anything. Built for compliance, finance and policy teams who use ChatGPT at work and need evidence of what
was asked and answered. It records only what the assistant sends it when you ask; it does not prove the
record is complete or that the text came from a particular person.

**Category:** Productivity / Business tools.   **Countries:** wherever you are comfortable (the directory
excludes the EEA, Switzerland and the UK by default).

**Authentication:** OAuth. Approving gives a random pseudonym; "Sign in with GitHub" optionally names you.

## Test cases to submit

Provide a test account instruction: "Connect the app and click Approve (no sign-in needed)."

Positive (expected behaviour in each):

1. "Seal this chat with the EPI Evidence Sealer." → the app is called, returns a view link, a download
   link and a SHA-256; the seal self-check shows integrity and signature valid.
2. "Seal only my last question and your answer." → a record with two messages is created.
3. "Save a tamper-evident audit record of this conversation and give me the SHA-256." → same result, with
   the hash shown.
4. After sealing: "Verify the file you just sealed." → the verify tool reports integrity and signature valid.
5. After sealing: "Show me the timeline of that sealed record." → the read-back tool lists the sealed messages.

Negative:

1. Use the app before approving it. → ChatGPT asks to connect; nothing is sealed.
2. "Verify the sealed file with id 0000000000000000." → a clear "not found" message; nothing is invented.
3. Ask it to seal a record far over the size limit (thousands of events). → a clear message to seal in
   parts; nothing is sealed.

## Likely review questions, and honest answers

- *Does it do something ChatGPT cannot already do?* Yes: it produces a cryptographically signed file with
  a hash chain that a third party can verify offline. ChatGPT can only produce text.
- *What does it write?* A new file on our server, kept 24 hours, deleted automatically. It changes nothing in
  the user's other systems. That is why it is marked a non-destructive write and closed-world.
- *What data does it receive?* Only what the assistant sends when the user asks to seal; the privacy
  policy lists it. Secrets and others' personal data should be replaced with `[REDACTED]`.
- *Reliability:* the free server sleeps when idle; for submission, use a plan that stays awake so reviewers
  are not met with a long first-load delay.

## Known gaps

- Per-tool `securitySchemes` declarations (an Apps SDK convention) are not added: the spec could not be read
  here. If review or a test asks for them, add them in `epi_mcp/server.py` (tool `meta`).
- A first review may ask for changes; budget a few rounds.
