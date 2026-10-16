import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { newApiKey, newId, nowIso, sha256Hex } from "../lib/crypto.ts";
import { membershipRole, userFromRequest } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";

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
  const body = z.object({ scopes: z.array(z.enum(SCOPES)).min(1), label: z.string().trim().min(1).max(80).optional() }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Scopes required (push, read)." } }, 400);
  const key = newApiKey();
  const id = newId("key");
  await c.env.DB.prepare(
    "INSERT INTO api_keys (id, org_id, prefix, key_hash, scopes, label, created_by, created_at, last_used_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
  )
    .bind(id, orgId, key.prefix, await sha256Hex(key.raw), [...new Set(body.data.scopes)].join(","), body.data.label ?? null, user.id, nowIso())
    .run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "api_key.create", detail: `${id} scopes=${body.data.scopes.join(",")}` });
  return c.json({ id, key: key.raw, prefix: key.prefix }, 201);
});

app.get("/orgs/:orgId/api-keys", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (role !== "owner") return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  const rows = await c.env.DB.prepare(
    "SELECT id, prefix, scopes, label, created_by, created_at, last_used_at, revoked_at FROM api_keys WHERE org_id = ? ORDER BY created_at",
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

export default app;
