import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { newId, nowIso, sha256Hex } from "../lib/crypto.ts";
import { keyFromRequest, membershipRole, userFromRequest } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";
import { limitAllows, planOf, retentionUntil } from "../lib/plans.ts";
import { verifyManifestSignature } from "../lib/manifest.ts";
import { createShareLink, trustLinkFromRequest } from "./shares.ts";

const app = new Hono<{ Bindings: Env }>();

export const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_MANIFEST_BYTES = 64 * 1024;

const reasonSchema = z.enum(["dispute", "sample", "audit_request", "other"]);

type Writer = { by: string };
type Reader = { by: string; scopeAgents: "all" | string[] | null };

async function writerAuth(db: D1Database, req: Request, orgId: string): Promise<Writer | null> {
  const key = await keyFromRequest(db, req);
  if (key && key.orgId === orgId && key.scopes.includes("push")) return { by: `key:${key.id}` };
  const user = await userFromRequest(db, req);
  if (!user) return null;
  const role = await membershipRole(db, orgId, user.id);
  if (role === "owner" || role === "member") return { by: `user:${user.id}` };
  return null;
}

/** Why a writer was refused, in customer words (401 for a dead key so the
 *  CLI can say "reconnect", 403 otherwise). */
async function writerDenied(db: D1Database, req: Request): Promise<{ status: 401 | 403; body: { error: { code: string; message: string } } }> {
  const h = req.headers.get("Authorization") ?? "";
  if (h.startsWith("Bearer epik_") && !(await keyFromRequest(db, req))) {
    return {
      status: 401,
      body: { error: { code: "key_invalid", message: "This computer's key was revoked or isn't valid for this workspace. Reconnect with: epi cloud login" } },
    };
  }
  return { status: 403, body: { error: { code: "forbidden", message: "Sign in to the dashboard, or connect this computer with: epi cloud login" } } };
}

async function readerAuth(db: D1Database, req: Request, orgId: string): Promise<Reader | null> {
  const user = await userFromRequest(db, req);
  if (user) {
    const role = await membershipRole(db, orgId, user.id);
    if (role) return { by: `user:${user.id}`, scopeAgents: null };
  }
  const key = await keyFromRequest(db, req);
  if (key && key.orgId === orgId && key.scopes.includes("read")) return { by: `key:${key.id}`, scopeAgents: null };
  const link = await trustLinkFromRequest(db, req);
  if (link && link.org_id === orgId) return { by: `share:${link.id}`, scopeAgents: link.scope.agents };
  return null;
}

function agentVisible(scopeAgents: "all" | string[] | null, agentId: string | null): boolean {
  if (scopeAgents === null || scopeAgents === "all") return true;
  return agentId !== null && scopeAgents.includes(agentId);
}

async function witnessStatus(
  db: D1Database,
  env: Env,
  orgId: string,
  workflowId: string | null,
  claimedSha256: string,
): Promise<string> {
  const inboxes = await db.prepare("SELECT id FROM inboxes WHERE org_id = ? AND closed_at IS NULL").bind(orgId).all<{ id: string }>();
  const ids = (inboxes.results ?? []).map((r) => r.id);
  if (!ids.length) return "no_inbox";
  if (!workflowId) return "not_in_witness";
  let seenWorkflow = false;
  for (const inboxId of ids) {
    try {
      const stub = env.WITNESS.get(env.WITNESS.idFromName(inboxId));
      const res = await stub.fetch(`https://inbox/find?workflow=${encodeURIComponent(workflowId)}`);
      if (!res.ok) continue;
      const { matches } = (await res.json()) as { matches: string[] };
      for (const raw of matches) {
        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(raw) as Record<string, unknown>;
        } catch {
          continue;
        }
        if (payload.workflow_id !== workflowId) continue;
        seenWorkflow = true;
        if (payload.file_sha256 === claimedSha256) return "witnessed";
      }
    } catch {
      // One unreachable inbox must not fail the push.
    }
  }
  return seenWorkflow ? "different_version" : "not_in_witness";
}

// Vendor pushes a SELECTED run: claims + manifest first, bytes second.
// The server never hashes or unzips the upload (10 ms CPU, plan §1.2).
app.post("/orgs/:orgId/artifacts/init", async (c) => {
  const orgId = c.req.param("orgId");
  const auth = await writerAuth(c.env.DB, c.req.raw, orgId);
  if (!auth) { const d = await writerDenied(c.env.DB, c.req.raw); return c.json(d.body, d.status); }
  const body = z.object({
    manifest_json: z.string().min(2).max(MAX_MANIFEST_BYTES),
    claimed_sha256: z.string().regex(/^[0-9a-f]{64}$/),
    claimed_crc32: z.number().int().min(0).max(4294967295),
    size_bytes: z.number().int().min(1).max(MAX_FILE_BYTES),
    agent: z.string().min(1).max(120).nullish(),
    reason: reasonSchema,
  }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "manifest_json, claimed_sha256, claimed_crc32, size_bytes, reason required." } }, 400);

  let manifest: Record<string, unknown>;
  try {
    manifest = JSON.parse(body.data.manifest_json) as Record<string, unknown>;
  } catch {
    return c.json({ error: { code: "bad_request", message: "manifest_json is not JSON." } }, 400);
  }
  const check = await verifyManifestSignature(body.data.manifest_json);
  if (check.status === "invalid" && check.reason?.startsWith("Legacy CBOR")) {
    return c.json({ error: { code: "unsupported_manifest", message: check.reason } }, 400);
  }
  const signatureCheck = check.status; // 'valid' | 'invalid' | 'unsigned'
  const fingerprint = check.status === "unsigned" ? null : (check as { fingerprint: string }).fingerprint ?? null;

  const org = await c.env.DB.prepare("SELECT plan FROM orgs WHERE id = ?").bind(orgId).first<{ plan: string }>();
  if (!org) return c.json({ error: { code: "not_found", message: "Org not found." } }, 404);
  const plan = planOf(org.plan);
  const fileCount = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM artifacts WHERE org_id = ? AND deleted_at IS NULL").bind(orgId).first<{ n: number }>();
  const room = limitAllows(plan, "evidenceFiles", fileCount?.n ?? 0);

  const dupe = await c.env.DB.prepare("SELECT id, agent_id, manifest_json, upload_state, witness_status, signature_check FROM artifacts WHERE org_id = ? AND claimed_sha256 = ?")
    .bind(orgId, body.data.claimed_sha256).first<{ id: string; agent_id: string | null; manifest_json: string; upload_state: string; witness_status: string; signature_check: string }>();
  if (dupe) {
    // Re-push of the same bytes: refresh the witness status (a late witness
    // report may have arrived since the first push) and fill in the customer
    // tag only when the stored run has none. An existing tag is never
    // replaced — moving a run between customers would leak it onto another
    // customer's reviewer link. An unknown customer name on re-push is
    // ignored (pre-existing runs keep working); it only 400s on first push.
    let agentId: string | null = null;
    if (body.data.agent) {
      const agent = await c.env.DB.prepare("SELECT id FROM agents WHERE org_id = ? AND name = ?").bind(orgId, body.data.agent).first<{ id: string }>();
      if (agent) agentId = agent.id;
    }
    // Refresh the witness status, but never downgrade: an unreachable or
    // closed inbox reads as "not found", which must not erase a "witnessed"
    // verdict for the same bytes.
    let workflowId: string | null = null;
    try {
      const dm = JSON.parse(dupe.manifest_json) as Record<string, unknown>;
      if (typeof dm.workflow_id === "string") workflowId = dm.workflow_id;
    } catch {
      // Unreadable manifest: keep the stored status.
    }
    const recomputed = workflowId ? await witnessStatus(c.env.DB, c.env, orgId, workflowId, body.data.claimed_sha256) : dupe.witness_status;
    const status = dupe.witness_status === "witnessed" ? "witnessed" : recomputed;
    const adopt = !dupe.agent_id && agentId ? agentId : dupe.agent_id;
    if (status !== dupe.witness_status || adopt !== dupe.agent_id) {
      await c.env.DB.prepare("UPDATE artifacts SET agent_id = ?, witness_status = ? WHERE id = ?").bind(adopt, status, dupe.id).run();
      await auditLog(d1AuditDb(c.env.DB), { orgId, actor: auth.by, action: adopt !== dupe.agent_id ? "artifact.assign" : "artifact.refresh", detail: `${dupe.id} ${status}` });
    }
    let agentLabel: string | null = null;
    if (adopt) {
      const nm = await c.env.DB.prepare("SELECT name FROM agents WHERE id = ?").bind(adopt).first<{ name: string }>();
      agentLabel = nm?.name ?? body.data.agent ?? null;
    }
    return c.json({
      id: dupe.id, deduped: true,
      put_url: dupe.upload_state === "stored" ? null : `/v1/orgs/${orgId}/artifacts/${dupe.id}/content`,
      witness_status: status, signature_check: dupe.signature_check, agent: agentLabel,
    });
  }
  if (!room.ok) return c.json({ error: { code: "plan_limit", message: room.message } }, 402);

  let agentId: string | null = null;
  if (body.data.agent) {
    const agent = await c.env.DB.prepare("SELECT id FROM agents WHERE org_id = ? AND name = ?").bind(orgId, body.data.agent).first<{ id: string }>();
    if (!agent) return c.json({ error: { code: "bad_request", message: `Unknown agent ${body.data.agent}.` } }, 400);
    agentId = agent.id;
  }

  const status = await witnessStatus(c.env.DB, c.env, orgId, typeof manifest.workflow_id === "string" ? manifest.workflow_id : null, body.data.claimed_sha256);
  const now = nowIso();
  const id = newId("art");
  await c.env.DB.prepare(
    "INSERT INTO artifacts (id, org_id, agent_id, claimed_sha256, claimed_crc32, size_bytes, manifest_json, spec_version, workflow_id, goal, steps, sealed_at, key_fingerprint, signature_check, witness_status, reason, object_key, upload_state, uploaded_at, retention_until, legal_hold, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, 0, NULL)",
  ).bind(
    id, orgId, agentId, body.data.claimed_sha256, body.data.claimed_crc32, body.data.size_bytes, body.data.manifest_json,
    typeof manifest.spec_version === "string" ? manifest.spec_version : null,
    typeof manifest.workflow_id === "string" ? manifest.workflow_id : null,
    typeof manifest.goal === "string" ? manifest.goal : null,
    typeof manifest.total_steps === "number" ? manifest.total_steps : null,
    typeof manifest.created_at === "string" ? manifest.created_at : null,
    fingerprint, signatureCheck, status, body.data.reason, `${orgId}/${id}.epi`, now, retentionUntil(plan, now),
  ).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: auth.by, action: "artifact.init", detail: `${id} ${body.data.reason} ${status}` });
  return c.json({ id, put_url: `/v1/orgs/${orgId}/artifacts/${id}/content`, witness_status: status, signature_check: signatureCheck, agent: body.data.agent ?? null }, 201);
});

// Byte upload, streamed straight to R2. Content-Length must match init.
app.put("/orgs/:orgId/artifacts/:artifactId/content", async (c) => {
  const orgId = c.req.param("orgId");
  const auth = await writerAuth(c.env.DB, c.req.raw, orgId);
  if (!auth) { const d = await writerDenied(c.env.DB, c.req.raw); return c.json(d.body, d.status); }
  const row = await c.env.DB.prepare("SELECT id, size_bytes, object_key, upload_state FROM artifacts WHERE id = ? AND org_id = ? AND deleted_at IS NULL")
    .bind(c.req.param("artifactId"), orgId).first<{ id: string; size_bytes: number; object_key: string; upload_state: string }>();
  if (!row) return c.json({ error: { code: "not_found", message: "Artifact not found." } }, 404);
  if (row.upload_state === "stored") return c.json({ error: { code: "conflict", message: "Already stored." } }, 409);
  const length = Number(c.req.header("Content-Length"));
  if (!Number.isFinite(length) || length !== row.size_bytes) {
    return c.json({ error: { code: "bad_request", message: `Content-Length must equal ${row.size_bytes}.` } }, 400);
  }
  if (!c.req.raw.body) return c.json({ error: { code: "bad_request", message: "Empty body." } }, 400);
  try {
    await c.env.ROOM.put(row.object_key, c.req.raw.body);
  } catch {
    return c.json({ error: { code: "internal", message: "Upload failed." } }, 500);
  }
  await c.env.DB.prepare("UPDATE artifacts SET upload_state = 'stored' WHERE id = ?").bind(row.id).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: auth.by, action: "artifact.store", detail: row.id });
  return c.json({ stored: true });
});

const listCols = "id, agent_id, claimed_sha256, size_bytes, workflow_id, goal, sealed_at, key_fingerprint, signature_check, witness_status, reason, upload_state, uploaded_at, retention_until, legal_hold";

app.get("/orgs/:orgId/artifacts", async (c) => {
  const orgId = c.req.param("orgId");
  const auth = await readerAuth(c.env.DB, c.req.raw, orgId);
  if (!auth) return c.json({ error: { code: "forbidden", message: "Member, read key, or share token required." } }, 403);
  const rows = await c.env.DB.prepare(`SELECT ${listCols} FROM artifacts WHERE org_id = ? AND deleted_at IS NULL ORDER BY uploaded_at DESC LIMIT 200`).bind(orgId).all<Record<string, unknown>>();
  const files = ((rows.results ?? []) as Array<Record<string, unknown> & { id: string; agent_id: string | null }>)
    .filter((r) => agentVisible(auth.scopeAgents, r.agent_id))
    .map((r) => ({ ...r, content_url: `/v1/orgs/${orgId}/artifacts/${r.id}/content` }));
  return c.json({ artifacts: files });
});

app.get("/orgs/:orgId/artifacts/:artifactId", async (c) => {
  const orgId = c.req.param("orgId");
  const auth = await readerAuth(c.env.DB, c.req.raw, orgId);
  if (!auth) return c.json({ error: { code: "forbidden", message: "Member, read key, or share token required." } }, 403);
  const row = await c.env.DB.prepare(`SELECT ${listCols} FROM artifacts WHERE id = ? AND org_id = ? AND deleted_at IS NULL`)
    .bind(c.req.param("artifactId"), orgId).first<Record<string, unknown> & { id: string; agent_id: string | null }>();
  if (!row || !agentVisible(auth.scopeAgents, row.agent_id)) {
    return c.json({ error: { code: "not_found", message: "Artifact not found." } }, 404);
  }
  return c.json({ ...row, content_url: `/v1/orgs/${orgId}/artifacts/${row.id}/content` });
});

app.get("/orgs/:orgId/artifacts/:artifactId/content", async (c) => {
  const orgId = c.req.param("orgId");
  const auth = await readerAuth(c.env.DB, c.req.raw, orgId);
  if (!auth) return c.json({ error: { code: "forbidden", message: "Member, read key, or share token required." } }, 403);
  const row = await c.env.DB.prepare("SELECT id, agent_id, object_key, upload_state FROM artifacts WHERE id = ? AND org_id = ? AND deleted_at IS NULL")
    .bind(c.req.param("artifactId"), orgId).first<{ id: string; agent_id: string | null; object_key: string; upload_state: string }>();
  if (!row || row.upload_state !== "stored" || !agentVisible(auth.scopeAgents, row.agent_id)) {
    return c.json({ error: { code: "not_found", message: "Artifact not found." } }, 404);
  }
  const obj = await c.env.ROOM.get(row.object_key);
  if (!obj) return c.json({ error: { code: "not_found", message: "File missing from storage." } }, 404);
  return new Response(obj.body, {
    headers: { "Content-Type": "application/octet-stream", "Content-Disposition": `attachment; filename="${row.id}.epi"` },
  });
});

app.post("/orgs/:orgId/artifacts/:artifactId/legal-hold", async (c) => {
  const orgId = c.req.param("orgId");
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  const body = z.object({ hold: z.boolean() }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "{hold: boolean} required." } }, 400);
  const res = await c.env.DB.prepare("UPDATE artifacts SET legal_hold = ? WHERE id = ? AND org_id = ? AND deleted_at IS NULL")
    .bind(body.data.hold ? 1 : 0, c.req.param("artifactId"), orgId).run();
  if (res.meta.changes === 0) return c.json({ error: { code: "not_found", message: "Artifact not found." } }, 404);
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: body.data.hold ? "artifact.hold" : "artifact.unhold", detail: c.req.param("artifactId") });
  return c.json({ ok: true });
});

// Assign an Unassigned run to a customer (dashboard only).
// Owner/member SESSION only — a computer's push key must never move runs:
// moving a run between customers would leak it onto another customer's
// share link. A run that already belongs to a customer stays there (409).
// Re-tagging never changes bytes, so the sha dedupe stays intact;
// witness_status is recomputed because the run may now match an inbox.
app.patch("/orgs/:orgId/artifacts/:artifactId/agent", async (c) => {
  const orgId = c.req.param("orgId");
  const user = await userFromRequest(c.env.DB, c.req.raw);
  const role = user ? await membershipRole(c.env.DB, orgId, user.id) : null;
  if (!user || (role !== "owner" && role !== "member")) {
    return c.json({ error: { code: "forbidden", message: "Only workspace owners and members can assign runs, from the dashboard." } }, 403);
  }
  const auth = { by: `user:${user.id}` };
  const body = z.object({ agent: z.string().min(1).max(120) }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Pick a customer." } }, 400);
  const row = await c.env.DB.prepare("SELECT id, agent_id, manifest_json, claimed_sha256 FROM artifacts WHERE id = ? AND org_id = ? AND deleted_at IS NULL")
    .bind(c.req.param("artifactId"), orgId).first<{ id: string; agent_id: string | null; manifest_json: string; claimed_sha256: string }>();
  if (!row) return c.json({ error: { code: "not_found", message: "That run no longer exists." } }, 404);
  const agent = await c.env.DB.prepare("SELECT id FROM agents WHERE org_id = ? AND name = ?").bind(orgId, body.data.agent).first<{ id: string }>();
  if (!agent) return c.json({ error: { code: "bad_request", message: `There is no customer called "${body.data.agent}".` } }, 400);
  if (row.agent_id && row.agent_id !== agent.id) {
    return c.json({ error: { code: "already_assigned", message: "This run already belongs to another customer and can't be moved." } }, 409);
  }
  let workflowId: string | null = null;
  try {
    const manifest = JSON.parse(row.manifest_json) as Record<string, unknown>;
    if (typeof manifest.workflow_id === "string") workflowId = manifest.workflow_id;
  } catch {
    // Keep the stored witness status if the manifest is unreadable.
  }
  const status = await witnessStatus(c.env.DB, c.env, orgId, workflowId, row.claimed_sha256);
  await c.env.DB.prepare("UPDATE artifacts SET agent_id = ?, witness_status = ? WHERE id = ?")
    .bind(agent.id, status, row.id).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: auth.by, action: "artifact.assign", detail: `${row.id} agent=${body.data.agent} ${status}` });
  return c.json({ id: row.id, agent_id: agent.id, witness_status: status });
});

app.delete("/orgs/:orgId/artifacts/:artifactId", async (c) => {
  const orgId = c.req.param("orgId");
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  const row = await c.env.DB.prepare("SELECT id, object_key, legal_hold FROM artifacts WHERE id = ? AND org_id = ? AND deleted_at IS NULL")
    .bind(c.req.param("artifactId"), orgId).first<{ id: string; object_key: string; legal_hold: number }>();
  if (!row) return c.json({ error: { code: "not_found", message: "Artifact not found." } }, 404);
  if (row.legal_hold) return c.json({ error: { code: "legal_hold", message: "Release the legal hold first." } }, 409);
  await c.env.ROOM.delete(row.object_key);
  await c.env.DB.prepare("UPDATE artifacts SET deleted_at = ? WHERE id = ?").bind(nowIso(), row.id).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "artifact.delete", detail: row.id });
  return c.json({ ok: true });
});

// "Export everything": a week-long trust link covering all agents/inboxes,
// the file list, and the witness exports — so a customer can leave any time.
app.post("/orgs/:orgId/export", async (c) => {
  const orgId = c.req.param("orgId");
  const user = await userFromRequest(c.env.DB, c.req.raw);
  let actor: string | null = null;
  if (user) {
    const role = await membershipRole(c.env.DB, orgId, user.id);
    if (role === "owner" || role === "member") actor = `user:${user.id}`;
  }
  if (!actor) {
    const key = await keyFromRequest(c.env.DB, c.req.raw);
    if (key && key.orgId === orgId && key.scopes.includes("push")) actor = `key:${key.id}`;
  }
  if (!actor) return c.json({ error: { code: "forbidden", message: "Member session or push key required." } }, 403);
  const { id, token } = await createShareLink(
    c.env.DB, orgId, `Full export ${nowIso().slice(0, 10)}`,
    { agents: "all", inboxes: "all" }, new Date(Date.now() + 7 * 86_400_000).toISOString(),
  );
  const files = await c.env.DB.prepare("SELECT id, claimed_sha256, size_bytes, workflow_id FROM artifacts WHERE org_id = ? AND deleted_at IS NULL ORDER BY uploaded_at DESC")
    .bind(orgId).all<Record<string, unknown>>();
  const inboxes = await c.env.DB.prepare("SELECT id, customer_label FROM inboxes WHERE org_id = ? ORDER BY created_at").bind(orgId).all<{ id: string; customer_label: string }>();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor, action: "export.create", detail: id });
  return c.json({
    share_url: `/t/${id}#k=${token}`,
    files: ((files.results ?? []) as Array<Record<string, unknown> & { id: string }>).map((f) => ({
      ...f, content_url: `/v1/orgs/${orgId}/artifacts/${f.id}/content`,
    })),
    witness_exports: ((inboxes.results ?? []) as Array<{ id: string; customer_label: string }>).map((i) => ({
      inbox_id: i.id, customer_label: i.customer_label, export_url: `/w/${i.id}/export.jsonl`, chain_url: `/w/${i.id}/chain.jsonl`,
    })),
  });
});

export default app;
