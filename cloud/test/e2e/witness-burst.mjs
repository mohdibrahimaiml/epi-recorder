// Real-runtime witness e2e (runs against `wrangler dev --local`).
// Seeds D1 directly, sends 200 concurrent signed receipts, and asserts:
// 200×202 with seqs exactly 1..200 (arrival-ordered), an intact recomputed
// chain over the committed payload set, byte-identical export, plus 401/400
// rejections. Exits non-zero on any failure.
//
// Env: E2E_BASE (default http://127.0.0.1:18787),
//      E2E_INBOX_SECRET_KEY (32-byte hex, also passed to wrangler --var).
// No Cloudflare account needed; nothing leaves the machine.

import { execFileSync } from "node:child_process";
import { createHash, createHmac, randomBytes } from "node:crypto";
import { join } from "node:path";

// wrangler's JS entrypoint directly: no shell, no PATH lookup (npx.cmd
// cannot be spawnSync'd on Windows without a shell).
const WRANGLER_JS = join(process.cwd(), "node_modules", "wrangler", "bin", "wrangler.js");

const BASE = process.env.E2E_BASE ?? "http://127.0.0.1:18787";
const BOX_KEY = process.env.E2E_INBOX_SECRET_KEY ?? "";
if (!/^[0-9a-f]{64}$/.test(BOX_KEY)) {
  console.error("E2E_INBOX_SECRET_KEY must be 32 bytes hex");
  process.exit(2);
}

const ORG = `o_e2e_${randomBytes(4).toString("hex")}`;
const INBOX = `inb_e2e_${randomBytes(4).toString("hex")}`;
const USER = `u_e2e_${randomBytes(4).toString("hex")}`;
const SESSION_RAW = randomBytes(32).toString("hex");
// The HMAC secret is an opaque string on both sides (like EPI_WITNESS_SECRET):
// sealed as UTF-8 text, and HMAC-signed as UTF-8 text. Never hex-decode it.
const HMAC_SECRET = process.env.E2E_HMAC_SECRET ?? randomBytes(24).toString("base64url");
const N = 200;

const fail = (msg) => {
  console.error(`E2E FAIL: ${msg}`);
  process.exit(1);
};

function wranglerD1(command) {
  return execFileSync(
    process.execPath,
    [WRANGLER_JS, "d1", "execute", "epi-cloud", "--local", "--config", "wrangler.toml", "--command", command, "--json"],
    { encoding: "utf8", timeout: 60000 },
  );
}

async function sealSecret(boxHex, plaintext) {
  const key = await crypto.subtle.importKey(
    "raw",
    Uint8Array.from(Buffer.from(boxHex, "hex")),
    { name: "AES-GCM" },
    false,
    ["encrypt"],
  );
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, new TextEncoder().encode(plaintext)),
  );
  return Buffer.from([...nonce, ...ct]).toString("base64");
}

function sha256Hex(s) {
  return createHash("sha256").update(s, "utf8").digest("hex");
}

async function main() {
  const enc = await sealSecret(BOX_KEY, HMAC_SECRET);
  const now = new Date().toISOString();
  const tag = randomBytes(4).toString("hex");
  const stmts = [
    `INSERT INTO orgs (id, slug, name, plan, created_at) VALUES ('${ORG}', 'e2e-${tag}', 'E2E', 'free', '${now}')`,
    `INSERT INTO users (id, email, display_name, created_at) VALUES ('${USER}', 'e2e@test', 'E2E', '${now}')`,
    `INSERT INTO sessions (id_hash, user_id, expires_at) VALUES ('${sha256Hex(SESSION_RAW)}', '${USER}', '2999-01-01T00:00:00.000Z')`,
    `INSERT INTO memberships (org_id, user_id, role) VALUES ('${ORG}', '${USER}', 'owner')`,
    `INSERT INTO inboxes (id, org_id, customer_label, hmac_secret_enc, created_at, closed_at) VALUES ('${INBOX}', '${ORG}', 'E2E Bank', '${enc}', '${now}', NULL)`,
  ];
  for (const sql of stmts) wranglerD1(sql);

  const hmac = (body) => createHmac("sha256", HMAC_SECRET).update(body, "utf8").digest("hex");

  const payloads = Array.from({ length: N }, (_, i) =>
    JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: `wf-${i}`, content_digest: `cd-${i}`, file_sha256: `fs-${i}` }),
  );

  const posts = await Promise.all(
    payloads.map(async (raw, i) => {
      const res = await fetch(`${BASE}/w/${INBOX}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmac(raw)}` },
        body: raw,
      });
      const json = await res.json().catch(() => ({}));
      return { i, status: res.status, seq: json.seq };
    }),
  );
  const bad = posts.filter((p) => p.status !== 202);
  if (bad.length) fail(`${bad.length} receipts not 202 (first: ${JSON.stringify(bad[0])})`);
  // Seqs must be exactly 1..N with no gaps or dupes. They need NOT match
  // submission order: concurrent appends serialize in arrival order.
  const seqs = posts.map((p) => p.seq).sort((a, b) => a - b);
  if (seqs.length !== N || seqs.some((s, i) => s !== i + 1)) fail(`seqs not exactly 1..${N}`);
  console.log(`receipts: ${N}x202, seqs exactly 1..${N} (arrival-ordered)`);

  const cookie = { Cookie: `epi_session=${SESSION_RAW}` };
  const chainText = await (await fetch(`${BASE}/w/${INBOX}/chain.jsonl`, { headers: cookie })).text();
  const envelopes = chainText.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
  const bySeq = new Map(envelopes.map((e) => [e.seq, e.payload_raw]));
  const sentSet = new Set(payloads);
  if (bySeq.size !== N || [...bySeq.values()].some((p) => !sentSet.has(p))) {
    fail("chain payloads do not match the sent set");
  }
  // Export must equal the committed log order (chain order), not send order.
  const expRes = await fetch(`${BASE}/w/${INBOX}/export.jsonl`, { headers: cookie });
  if (expRes.status !== 200) fail(`export status ${expRes.status}`);
  const expText = await expRes.text();
  const wantText = envelopes.map((e) => e.payload_raw).join("\n") + "\n";
  if (expText !== wantText) fail("export.jsonl differs from the committed chain order");
  console.log("export: byte-identical to the committed chain");
  let prev = "GENESIS";
  for (const e of envelopes) {
    if (e.prev_hash !== prev) fail(`chain link broken at seq ${e.seq}`);
    const inner = sha256Hex(e.payload_raw);
    const recomputed = sha256Hex(`${prev}${inner}${e.received_at}`);
    if (recomputed !== e.entry_hash) fail(`entry_hash mismatch at seq ${e.seq}`);
    prev = e.entry_hash;
  }
  if (envelopes.length !== N) fail(`chain has ${envelopes.length} entries, want ${N}`);
  console.log(`chain: ${N} links recomputed, intact`);

  const badSig = await fetch(`${BASE}/w/${INBOX}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-EPI-Signature": "sha256=00" },
    body: payloads[0],
  });
  if (badSig.status !== 401) fail(`bad HMAC gave ${badSig.status}, want 401`);
  const badBody = JSON.stringify({ schema: "nope" });
  const badSchema = await fetch(`${BASE}/w/${INBOX}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmac(badBody)}` },
    body: badBody,
  });
  if (badSchema.status !== 400) fail(`bad schema gave ${badSchema.status}, want 400`);
  console.log("rejections: 401 bad HMAC, 400 bad schema");
  console.log("E2E OK");
}

main().catch((err) => fail(String(err?.message ?? err)));
