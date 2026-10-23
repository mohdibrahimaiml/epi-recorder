import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { newId, newToken, nowIso } from "../lib/crypto.ts";
import { keyFromRequest, membershipRole, userFromRequest } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";
import { openSecret, sealSecret } from "../lib/secretbox.ts";
import { limitAllows, planOf } from "../lib/plans.ts";
import { ensureCustomerInbox } from "../lib/customerInbox.ts";

const app = new Hono<{ Bindings: Env }>();

export async function inboxSecret(db: D1Database, env: Env, inboxId: string): Promise<string | null> {
  const row = await db.prepare("SELECT hmac_secret_enc FROM inboxes WHERE id = ?").bind(inboxId).first<{ hmac_secret_enc: string }>();
  if (!row || !env.INBOX_SECRET_KEY) return null;
  return openSecret(env.INBOX_SECRET_KEY, row.hmac_secret_enc);
}

// Owner creates a witness inbox. URL + HMAC secret shown ONCE.
app.post("/orgs/:orgId/inboxes", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  if (!c.env.INBOX_SECRET_KEY) {
    return c.json({ error: { code: "not_configured", message: "Inbox encryption is not configured yet." } }, 503);
  }
  const body = z.object({ customer_label: z.string().min(1).max(120) }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Type the customer's name." } }, 400);
  const org = await c.env.DB.prepare("SELECT plan FROM orgs WHERE id = ?").bind(orgId).first<{ plan: string }>();
  if (!org) return c.json({ error: { code: "not_found", message: "Org not found." } }, 404);
  const open = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM inboxes WHERE org_id = ? AND closed_at IS NULL").bind(orgId).first<{ n: number }>();
  const allow = limitAllows(planOf(org.plan), "inboxes", open?.n ?? 0);
  if (!allow.ok) return c.json({ error: { code: "plan_limit", message: allow.message } }, 402);
  const id = newId("inb");
  const secret = newToken();
  await c.env.DB.prepare("INSERT INTO inboxes (id, org_id, customer_label, hmac_secret_enc, created_at, closed_at) VALUES (?, ?, ?, ?, ?, NULL)")
    .bind(id, orgId, body.data.customer_label, await sealSecret(c.env.INBOX_SECRET_KEY, secret), nowIso())
    .run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "inbox.create", detail: `${id} for ${body.data.customer_label}` });
  return c.json({ id, url: `${c.env.PUBLIC_WITNESS_URL}/w/${id}`, secret }, 201);
});

app.get("/orgs/:orgId/inboxes", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (!role) return c.json({ error: { code: "forbidden", message: "No access to this org." } }, 403);
  const rows = await c.env.DB.prepare("SELECT id, customer_label, created_at, closed_at FROM inboxes WHERE org_id = ? ORDER BY created_at").bind(orgId).all();
  return c.json({ inboxes: rows.results });
});

app.post("/orgs/:orgId/inboxes/:inboxId/close", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Only workspace owners can close a customer." } }, 403);
  }
  const inbox = await c.env.DB.prepare("SELECT customer_label FROM inboxes WHERE id = ? AND org_id = ? AND closed_at IS NULL")
    .bind(c.req.param("inboxId"), orgId).first<{ customer_label: string }>();
  if (!inbox) return c.json({ error: { code: "not_found", message: "That customer is already closed." } }, 404);
  await c.env.DB.prepare("UPDATE inboxes SET closed_at = ? WHERE id = ? AND org_id = ? AND closed_at IS NULL")
    .bind(nowIso(), c.req.param("inboxId"), orgId).run();
  // The customer's recorder name goes with it, so a closed customer stops
  // counting toward the plan (past runs keep their tag; links still show them).
  await c.env.DB.prepare("UPDATE agents SET status = 'archived' WHERE org_id = ? AND name = ? AND status = 'active'")
    .bind(orgId, inbox.customer_label).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "inbox.close", detail: c.req.param("inboxId") });
  return c.json({ ok: true });
});

// Owner reopens a closed customer (same witness inbox and secret, so
// computers that still have the old settings work again). Plan limits apply.
app.post("/orgs/:orgId/inboxes/:inboxId/reopen", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Only workspace owners can reopen a customer." } }, 403);
  }
  const inbox = await c.env.DB.prepare("SELECT customer_label FROM inboxes WHERE id = ? AND org_id = ? AND closed_at IS NOT NULL")
    .bind(c.req.param("inboxId"), orgId).first<{ customer_label: string }>();
  if (!inbox) return c.json({ error: { code: "not_found", message: "That customer is already open." } }, 404);
  const same = await c.env.DB.prepare("SELECT id FROM inboxes WHERE org_id = ? AND lower(customer_label) = lower(?) AND closed_at IS NULL")
    .bind(orgId, inbox.customer_label).first<{ id: string }>();
  if (same) return c.json({ error: { code: "conflict", message: `An open customer called "${inbox.customer_label}" already exists.` } }, 409);
  const org = await c.env.DB.prepare("SELECT plan FROM orgs WHERE id = ?").bind(orgId).first<{ plan: string }>();
  const open = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM inboxes WHERE org_id = ? AND closed_at IS NULL").bind(orgId).first<{ n: number }>();
  const allow = limitAllows(planOf(org?.plan), "inboxes", open?.n ?? 0);
  if (!allow.ok) return c.json({ error: { code: "plan_limit", message: allow.message } }, 402);
  await c.env.DB.prepare("UPDATE inboxes SET closed_at = NULL WHERE id = ? AND org_id = ?").bind(c.req.param("inboxId"), orgId).run();
  await c.env.DB.prepare("UPDATE agents SET status = 'active' WHERE org_id = ? AND name = ?").bind(orgId, inbox.customer_label).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "inbox.reopen", detail: c.req.param("inboxId") });
  return c.json({ ok: true });
});

// Owner rotates a witness inbox secret. New URL + HMAC secret shown ONCE.
// The old secret stops working immediately: every recorder reporting to this
// inbox must update EPI_WITNESS_SECRET. Runs already witnessed stay valid
// (the chain keeps every line that was accepted under the old secret).
// Queued recorder reports are HMAC-signed at send time (the secret is never
// stored in the outbox), so a queue drained with the new secret delivers.
app.post("/orgs/:orgId/inboxes/:inboxId/rotate", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  if (!c.env.INBOX_SECRET_KEY) {
    return c.json({ error: { code: "not_configured", message: "Inbox encryption is not configured yet." } }, 503);
  }
  const inboxId = c.req.param("inboxId");
  const row = await c.env.DB.prepare("SELECT org_id, closed_at FROM inboxes WHERE id = ?").bind(inboxId)
    .first<{ org_id: string; closed_at: string | null }>();
  if (!row || row.org_id !== orgId) {
    return c.json({ error: { code: "not_found", message: "Inbox not found." } }, 404);
  }
  if (row.closed_at) {
    return c.json({ error: { code: "inbox_closed", message: "Inbox is closed." } }, 410);
  }
  const secret = newToken();
  const res = await c.env.DB.prepare("UPDATE inboxes SET hmac_secret_enc = ? WHERE id = ? AND org_id = ?")
    .bind(await sealSecret(c.env.INBOX_SECRET_KEY, secret), inboxId, orgId).run();
  if (res.meta.changes === 0) return c.json({ error: { code: "not_found", message: "Inbox not found." } }, 404);
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "inbox.rotate", detail: `${inboxId}` });
  return c.json({ id: inboxId, url: `${c.env.PUBLIC_WITNESS_URL}/w/${inboxId}`, secret }, 200);
});

// Resolve (or, for owners, create) the recorder identity + witness inbox
// for one customer name. Used by `epi cloud use` and the device flow so a
// computer learns its witness settings without anyone copying a secret.
// Least privilege: push keys never get secrets here (they only learn the
// secret once via their own device login). Session owners get secrets
// (audited); members may resolve ids/urls but never secrets.
app.post("/orgs/:orgId/inboxes/by-customer", async (c) => {
  const orgId = c.req.param("orgId");
  const key = await keyFromRequest(c.env.DB, c.req.raw);
  if (key && key.orgId === orgId && key.scopes.includes("push")) {
    return c.json({ error: { code: "forbidden", message: "Ask an owner to connect this computer to that customer (or re-run epi cloud login)." } }, 403);
  }
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (role !== "owner" && role !== "member") return c.json({ error: { code: "forbidden", message: "Owners or members only." } }, 403);
  const actor = `user:${user.id}`;
  const body = z.object({ customer_label: z.string().min(1).max(120) }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Type the customer's name." } }, 400);
  const res = await ensureCustomerInbox(c.env.DB, c.env, orgId, body.data.customer_label, actor, {
    allowCreateInbox: role === "owner",
    allowCreateAgent: role === "owner" || role === "member",
  });
  if (!res.ok) return c.json({ error: { code: res.code, message: res.message } }, res.status as 400);
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor, action: "inbox.resolve", detail: `${res.inboxId} for ${body.data.customer_label.trim()}` });
  if (role !== "owner") {
    return c.json({ id: res.inboxId, agent_id: res.agentId, label: res.label, url: res.url, secret: null, created: res.created }, res.created ? 201 : 200);
  }
  return c.json({ id: res.inboxId, agent_id: res.agentId, label: res.label, url: res.url, secret: res.secret, created: res.created }, res.created ? 201 : 200);
});

export default app;
