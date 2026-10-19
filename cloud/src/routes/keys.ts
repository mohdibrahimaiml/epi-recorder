import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { newApiKey, newId, nowIso, sha256Hex } from "../lib/crypto.ts";
import { keyFromRequest, membershipRole, userFromRequest } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";
import { ensureCustomerInbox } from "../lib/customerInbox.ts";


const app = new Hono<{ Bindings: Env }>();
const SCOPES = ["push", "read"] as const;

// Owner mints `epik_…` (sha256 stored, raw shown once, scopes push/read).
// Optional label names the key (e.g. a computer's device name).
app.post("/orgs/:orgId/api-keys", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (role !== "owner") return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  const body = z.object({
    scopes: z.array(z.enum(SCOPES)).min(1),
    label: z.string().trim().min(1).max(80).optional(),
    // CI / automation: bind the key to a customer so its runs are tagged and
    // witnessed. The witness URL + secret come back once, with the key.
    customer_label: z.string().trim().min(1).max(120).optional(),
  }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Pick what the key can do (upload runs, read runs)." } }, 400);
  let customer: { label: string; url: string; secret: string } | null = null;
  if (body.data.customer_label) {
    const ensured = await ensureCustomerInbox(c.env.DB, c.env, orgId, body.data.customer_label, `user:${user.id}`, {
      allowCreateInbox: true,
      allowCreateAgent: true,
    });
    if (!ensured.ok) return c.json({ error: { code: ensured.code, message: ensured.message } }, ensured.status as 400);
    customer = { label: ensured.label, url: ensured.url, secret: ensured.secret };
  }
  const key = newApiKey();
  const id = newId("key");
  await c.env.DB.prepare(
    "INSERT INTO api_keys (id, org_id, prefix, key_hash, scopes, label, created_by, created_at, last_used_at, revoked_at, customer_label) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)",
  )
    .bind(id, orgId, key.prefix, await sha256Hex(key.raw), [...new Set(body.data.scopes)].join(","), body.data.label ?? null, user.id, nowIso(), customer?.label ?? null)
    .run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "api_key.create", detail: `${id} scopes=${body.data.scopes.join(",")}${customer ? ` customer=${customer.label}` : ""}` });
  return c.json({
    id, key: key.raw, prefix: key.prefix,
    ...(customer ? { customer_label: customer.label, witness_url: customer.url, witness_secret: customer.secret } : {}),
  }, 201);
});

app.get("/orgs/:orgId/api-keys", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (role !== "owner") return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  const rows = await c.env.DB.prepare(
    "SELECT id, prefix, scopes, label, customer_label, created_by, created_at, last_used_at, revoked_at FROM api_keys WHERE org_id = ? ORDER BY created_at",
  ).bind(orgId).all();
  return c.json({ keys: rows.results });
});

app.delete("/orgs/:orgId/api-keys/:keyId", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (role !== "owner") return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  const res = await c.env.DB.prepare("UPDATE api_keys SET revoked_at = ? WHERE id = ? AND org_id = ? AND revoked_at IS NULL")
    .bind(nowIso(), c.req.param("keyId"), orgId).run();
  if (res.meta.changes === 0) return c.json({ error: { code: "not_found", message: "Key not found." } }, 404);
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "api_key.revoke", detail: c.req.param("keyId") });
  return c.json({ ok: true });
});

// Who am I? Works for a dashboard session or any API key (push-only keys
// included), so `epi cloud login --api-key …` can validate a CI key.
app.get("/orgs/:orgId/whoami", async (c) => {
  const orgId = c.req.param("orgId");
  const key = await keyFromRequest(c.env.DB, c.req.raw);
  if (key) {
    if (key.orgId !== orgId) return c.json({ error: { code: "forbidden", message: "This key belongs to a different workspace." } }, 403);
    const row = await c.env.DB.prepare("SELECT prefix, customer_label FROM api_keys WHERE id = ?").bind(key.id).first<{ prefix: string; customer_label: string | null }>();
    const org = await c.env.DB.prepare("SELECT name FROM orgs WHERE id = ?").bind(orgId).first<{ name: string }>();
    return c.json({ org_id: orgId, org_name: org?.name ?? null, kind: "key", scopes: key.scopes, key_prefix: row?.prefix ?? null, customer_label: row?.customer_label ?? null });
  }
  if ((c.req.header("Authorization") ?? "").startsWith("Bearer epik_")) {
    return c.json({ error: { code: "key_invalid", message: "This key was revoked or isn't valid. Reconnect with: epi cloud login" } }, 401);
  }
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (!role) return c.json({ error: { code: "forbidden", message: "You're not in this workspace." } }, 403);
  const org = await c.env.DB.prepare("SELECT name FROM orgs WHERE id = ?").bind(orgId).first<{ name: string }>();
  return c.json({ org_id: orgId, org_name: org?.name ?? null, kind: "session", role, scopes: null, key_prefix: null, customer_label: null });
});

export default app;
