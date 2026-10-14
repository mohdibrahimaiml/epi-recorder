import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { newId, newToken, nowIso, sha256Hex } from "../lib/crypto.ts";
import { membershipRole, userFromRequest } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";

const app = new Hono<{ Bindings: Env }>();
const INVITE_TTL_MS = 7 * 86_400_000;

// Owner creates an invite link (copy-paste; no email service needed).
app.post("/orgs/:orgId/invites", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (role !== "owner") return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  const body = z.object({ email: z.string().email().max(254), role: z.enum(["owner", "member", "viewer"]) }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Email and role required." } }, 400);
  const raw = newToken();
  const id = newId("inv");
  const expiresAt = new Date(Date.now() + INVITE_TTL_MS).toISOString();
  await c.env.DB.prepare("INSERT INTO invites (id, org_id, email, role, token_hash, expires_at, accepted_at) VALUES (?, ?, ?, ?, ?, ?, NULL)")
    .bind(id, orgId, body.data.email.toLowerCase(), body.data.role, await sha256Hex(raw), expiresAt)
    .run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "invite.create", detail: `${body.data.email} as ${body.data.role}` });
  return c.json({ id, token: raw, expires_at: expiresAt }, 201); // token shown once
});

// Invited user accepts (must be signed in).
app.post("/invites/:token/accept", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const inv = await c.env.DB.prepare("SELECT id, org_id, role, expires_at, accepted_at FROM invites WHERE token_hash = ?")
    .bind(await sha256Hex(c.req.param("token")))
    .first<{ id: string; org_id: string; role: "owner" | "member" | "viewer"; expires_at: string; accepted_at: string | null }>();
  if (!inv || inv.accepted_at || inv.expires_at <= nowIso()) {
    return c.json({ error: { code: "not_found", message: "Invite invalid or expired." } }, 404);
  }
  await c.env.DB.prepare("INSERT INTO memberships (org_id, user_id, role) VALUES (?, ?, ?) ON CONFLICT(org_id, user_id) DO UPDATE SET role = excluded.role")
    .bind(inv.org_id, user.id, inv.role)
    .run();
  await c.env.DB.prepare("UPDATE invites SET accepted_at = ? WHERE id = ?").bind(nowIso(), inv.id).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId: inv.org_id, actor: `user:${user.id}`, action: "invite.accept", detail: inv.id });
  return c.json({ org_id: inv.org_id, role: inv.role });
});

export default app;
