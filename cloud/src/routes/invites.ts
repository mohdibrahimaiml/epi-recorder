import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { newId, newToken, nowIso, sha256Hex } from "../lib/crypto.ts";
import { membershipRole, userFromRequest } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";

const app = new Hono<{ Bindings: Env }>();
const INVITE_TTL_MS = 7 * 86_400_000;

type Role = "owner" | "member" | "viewer";

/** Accept page for an invite link (served by the auth router at /auth/invite/:token). */
export function inviteUrl(env: Env, token: string): string {
  return `${env.APP_ORIGIN}/auth/invite/${token}`;
}

// Owner creates an invite link (copy-paste; no email service needed).
app.post("/orgs/:orgId/invites", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (role !== "owner") return c.json({ error: { code: "forbidden", message: "Only workspace owners can invite people." } }, 403);
  const body = z.object({ email: z.string().trim().email().max(254), role: z.enum(["owner", "member", "viewer"]) }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Type the person's email address and pick a role." } }, 400);
  const raw = newToken();
  const id = newId("inv");
  const expiresAt = new Date(Date.now() + INVITE_TTL_MS).toISOString();
  await c.env.DB.prepare("INSERT INTO invites (id, org_id, email, role, token_hash, expires_at, accepted_at) VALUES (?, ?, ?, ?, ?, ?, NULL)")
    .bind(id, orgId, body.data.email.toLowerCase(), body.data.role, await sha256Hex(raw), expiresAt)
    .run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "invite.create", detail: `${body.data.email} as ${body.data.role}` });
  // Token shown once; the url is the human accept page.
  return c.json({ id, token: raw, url: inviteUrl(c.env, raw), expires_at: expiresAt }, 201);
});

// Owner: pending (unaccepted, unexpired) invites.
app.get("/orgs/:orgId/invites", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Only workspace owners can see invites." } }, 403);
  }
  const rows = await c.env.DB.prepare(
    "SELECT id, email, role, expires_at FROM invites WHERE org_id = ? AND accepted_at IS NULL AND expires_at > ? ORDER BY expires_at DESC",
  ).bind(orgId, nowIso()).all();
  return c.json({ invites: rows.results ?? [] });
});

// Owner: cancel a pending invite (expire it now).
app.delete("/orgs/:orgId/invites/:inviteId", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Only workspace owners can cancel invites." } }, 403);
  }
  const res = await c.env.DB.prepare("UPDATE invites SET expires_at = ? WHERE id = ? AND org_id = ? AND accepted_at IS NULL")
    .bind(nowIso(), c.req.param("inviteId"), orgId)
    .run();
  if (!res.meta.changes) return c.json({ error: { code: "not_found", message: "That invite was already used or cancelled." } }, 404);
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "invite.revoke", detail: c.req.param("inviteId") });
  return c.json({ ok: true });
});

// Members of a workspace (owner + member can see who is in it).
app.get("/orgs/:orgId/members", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (role !== "owner" && role !== "member") {
    return c.json({ error: { code: "forbidden", message: "Only owners and members can see the team." } }, 403);
  }
  const rows = await c.env.DB.prepare(
    "SELECT m.user_id AS user_id, u.email AS email, m.role AS role FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.org_id = ? ORDER BY m.role, u.email",
  ).bind(orgId).all();
  return c.json({ members: rows.results ?? [] });
});

// Owner removes someone. The last owner can never be removed.
app.delete("/orgs/:orgId/members/:userId", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Only workspace owners can remove people." } }, 403);
  }
  const target = c.req.param("userId");
  const targetRole = await membershipRole(c.env.DB, orgId, target);
  if (!targetRole) return c.json({ error: { code: "not_found", message: "That person isn't in this workspace." } }, 404);
  if (targetRole === "owner") {
    const owners = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM memberships WHERE org_id = ? AND role = 'owner'").bind(orgId).first<{ n: number }>();
    if ((owners?.n ?? 0) <= 1) {
      return c.json({ error: { code: "last_owner", message: "A workspace needs at least one owner. Make someone else an owner first." } }, 409);
    }
  }
  await c.env.DB.prepare("DELETE FROM memberships WHERE org_id = ? AND user_id = ?").bind(orgId, target).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "member.remove", detail: target });
  return c.json({ ok: true });
});

/** Look up a live invite by its raw token (null when unknown, used or expired). */
export async function liveInvite(
  db: D1Database,
  token: string,
): Promise<{ id: string; org_id: string; email: string; role: Role; expires_at: string } | null> {
  const inv = await db.prepare("SELECT id, org_id, email, role, expires_at, accepted_at FROM invites WHERE token_hash = ?")
    .bind(await sha256Hex(token))
    .first<{ id: string; org_id: string; email: string; role: Role; expires_at: string; accepted_at: string | null }>();
  if (!inv || inv.accepted_at || inv.expires_at <= nowIso()) return null;
  return inv;
}

// Invited user accepts (must be signed in AS THE INVITED EMAIL). Without the
// email check, anyone holding a forwarded link (or any signed-in account)
// could join — even as owner.
app.post("/invites/:token/accept", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const inv = await liveInvite(c.env.DB, c.req.param("token"));
  if (!inv) return c.json({ error: { code: "not_found", message: "This invite is invalid, already used, or expired. Ask for a new one." } }, 404);
  if (!user.email || user.email.trim().toLowerCase() !== inv.email.trim().toLowerCase()) {
    return c.json({
      error: {
        code: "wrong_account",
        message: `This invite is for ${inv.email}. Sign out and sign in with that account to accept it.`,
      },
    }, 403);
  }
  const existing = await membershipRole(c.env.DB, inv.org_id, user.id);
  if (existing === "owner" && inv.role !== "owner") {
    // Never let an invite demote an existing owner (could orphan the workspace).
    await c.env.DB.prepare("UPDATE invites SET accepted_at = ? WHERE id = ?").bind(nowIso(), inv.id).run();
    return c.json({ org_id: inv.org_id, role: existing });
  }
  await c.env.DB.prepare("INSERT INTO memberships (org_id, user_id, role) VALUES (?, ?, ?) ON CONFLICT(org_id, user_id) DO UPDATE SET role = excluded.role")
    .bind(inv.org_id, user.id, inv.role)
    .run();
  await c.env.DB.prepare("UPDATE invites SET accepted_at = ? WHERE id = ?").bind(nowIso(), inv.id).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId: inv.org_id, actor: `user:${user.id}`, action: "invite.accept", detail: inv.id });
  return c.json({ org_id: inv.org_id, role: inv.role });
});

export default app;
