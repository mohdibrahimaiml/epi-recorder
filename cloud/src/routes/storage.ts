import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { nowIso } from "../lib/crypto.ts";
import { keyFromRequest, membershipRole, userFromRequest } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";

const app = new Hono<{ Bindings: Env }>();

const targetSchema = z.object({
  kind: z.enum(["s3", "r2"]),
  endpoint: z.string().url().max(300),
  bucket: z.string().min(1).max(63),
  region: z.string().min(1).max(32).nullish(),
  prefix: z.string().max(200).nullish(),
  object_lock: z.enum(["on", "off", "unknown"]).default("unknown"),
});

// Owner registers the customer-owned bucket. Secrets are never accepted
// here: credentials live in the vendor's environment, never at EPI Cloud.
app.put("/orgs/:orgId/storage-target", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  const raw = (await c.req.json().catch(() => null)) as Record<string, unknown> | null;
  if (raw && ["access_key", "secret", "api_key", "token", "password"].some((k) => k in raw)) {
    return c.json({ error: { code: "bad_request", message: "Credentials do not belong here; they stay in your environment." } }, 400);
  }
  const body = targetSchema.safeParse(raw);
  if (!body.success) return c.json({ error: { code: "bad_request", message: "kind, endpoint, bucket required." } }, 400);
  await c.env.DB.prepare(
    "INSERT INTO storage_targets (org_id, kind, endpoint, bucket, region, prefix, object_lock, last_check_at, last_check_ok) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL) " +
      "ON CONFLICT(org_id) DO UPDATE SET kind = excluded.kind, endpoint = excluded.endpoint, bucket = excluded.bucket, region = excluded.region, prefix = excluded.prefix, object_lock = excluded.object_lock",
  ).bind(orgId, body.data.kind, body.data.endpoint, body.data.bucket, body.data.region ?? null, body.data.prefix ?? null, body.data.object_lock).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "storage_target.set", detail: `${body.data.kind}:${body.data.bucket}` });
  return c.json({ ok: true });
});

app.get("/orgs/:orgId/storage-target", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (!role) return c.json({ error: { code: "forbidden", message: "No access to this org." } }, 403);
  const row = await c.env.DB.prepare(
    "SELECT kind, endpoint, bucket, region, prefix, object_lock, last_check_at, last_check_ok FROM storage_targets WHERE org_id = ?",
  ).bind(orgId).first<Record<string, unknown>>();
  return c.json({ target: row ?? null });
});

const checkSchema = z.object({
  ok: z.boolean(),
  count: z.number().int().min(0),
  object_lock: z.enum(["on", "off", "unknown"]).default("unknown"),
});

// Vendor-reported heartbeat from the recorder (no file data, no secrets).
app.post("/orgs/:orgId/storage-target/check", async (c) => {
  const orgId = c.req.param("orgId");
  const key = await keyFromRequest(c.env.DB, c.req.raw);
  if (!key || key.orgId !== orgId || !key.scopes.includes("push")) {
    return c.json({ error: { code: "forbidden", message: "Push API key required." } }, 403);
  }
  const body = checkSchema.safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "{ok, count} required." } }, 400);
  const res = await c.env.DB.prepare("UPDATE storage_targets SET last_check_at = ?, last_check_ok = ?, object_lock = ? WHERE org_id = ?")
    .bind(nowIso(), body.data.ok ? 1 : 0, body.data.object_lock, orgId).run();
  if (res.meta.changes === 0) return c.json({ error: { code: "not_found", message: "Register the storage target first." } }, 404);
  return c.json({ ok: true });
});

export default app;
