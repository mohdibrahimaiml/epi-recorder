import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { newId, nowIso } from "../lib/crypto.ts";
import { keyFingerprint } from "../lib/manifest.ts";
import { membershipRole, userFromRequest } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";

const app = new Hono<{ Bindings: Env }>();

const HEX64 = /^[0-9a-fA-F]{64}$/;

// Owner registers a PUBLIC key. Anything else (private keys, junk, wrong
// length) is refused: this registry is informational only, never a pin.
app.post("/orgs/:orgId/keys", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  const org = await c.env.DB.prepare("SELECT id, slug FROM orgs WHERE id = ?").bind(orgId).first<{ id: string; slug: string }>();
  if (!org) return c.json({ error: { code: "not_found", message: "Org not found." } }, 404);
  const body = z.object({ public_key: z.string().min(1).max(128), label: z.string().min(1).max(80).nullish() }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "public_key required." } }, 400);
  const pub = body.data.public_key.trim().toLowerCase();
  if (!HEX64.test(pub)) {
    return c.json({ error: { code: "bad_request", message: "public_key must be 64 hex chars (a .pub file, never a private key)." } }, 400);
  }
  const fingerprint = await keyFingerprint(pub);
  const id = newId("key");
  try {
    await c.env.DB.prepare(
      "INSERT INTO org_keys (id, org_id, public_key, fingerprint, label, valid_from, revoked_at, revoke_reason) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)",
    ).bind(id, orgId, pub, fingerprint, body.data.label ?? null, nowIso()).run();
  } catch {
    return c.json({ error: { code: "conflict", message: "Key already registered." } }, 409);
  }
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "org_key.register", detail: `${fingerprint}` });
  return c.json({ id, fingerprint }, 201);
});

app.get("/orgs/:orgId/keys", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  const rows = await c.env.DB.prepare(
    "SELECT id, public_key, fingerprint, label, valid_from, revoked_at FROM org_keys WHERE org_id = ? ORDER BY valid_from",
  ).bind(orgId).all();
  return c.json({ keys: rows.results });
});

app.post("/orgs/:orgId/keys/:keyId/revoke", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  const body = z.object({ reason: z.string().max(200).nullish() }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Invalid body." } }, 400);
  const res = await c.env.DB.prepare("UPDATE org_keys SET revoked_at = ?, revoke_reason = ? WHERE id = ? AND org_id = ? AND revoked_at IS NULL")
    .bind(nowIso(), body.data.reason ?? null, c.req.param("keyId"), orgId).run();
  if (res.meta.changes === 0) return c.json({ error: { code: "not_found", message: "Active key not found." } }, 404);
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "org_key.revoke", detail: c.req.param("keyId") });
  return c.json({ ok: true });
});

app.delete("/orgs/:orgId/keys/:keyId", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  const res = await c.env.DB.prepare("DELETE FROM org_keys WHERE id = ? AND org_id = ?").bind(c.req.param("keyId"), orgId).run();
  if (res.meta.changes === 0) return c.json({ error: { code: "not_found", message: "Key not found." } }, 404);
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "org_key.delete", detail: c.req.param("keyId") });
  return c.json({ ok: true });
});

export default app;

export const publicKeys = new Hono<{ Bindings: Env }>();

// Public key history by org slug. Informational only: reviewers still pin
// keys out of band (fingerprint confirmed with the sender).
publicKeys.get("/o/:slug/keys.json", async (c) => {
  const org = await c.env.DB.prepare("SELECT id FROM orgs WHERE slug = ?").bind(c.req.param("slug")).first<{ id: string }>();
  if (!org) return c.json({ error: { code: "not_found", message: "Unknown org." } }, 404);
  const rows = await c.env.DB.prepare(
    "SELECT public_key, fingerprint, label, valid_from, revoked_at FROM org_keys WHERE org_id = ? ORDER BY valid_from",
  ).bind(org.id).all();
  return c.json({ org: c.req.param("slug"), keys: rows.results });
});
