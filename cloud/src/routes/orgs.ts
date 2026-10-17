import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { newId, nowIso } from "../lib/crypto.ts";
import { membershipRole, userFromRequest, type Role } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";
import { limitAllows, planOf } from "../lib/plans.ts";

const app = new Hono<{ Bindings: Env }>();

const slugRe = /^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/;

async function needRole(
  db: D1Database,
  orgId: string,
  userId: string,
  roles: Role[],
): Promise<{ ok: true; role: Role } | { ok: false; status: 403 | 404 }> {
  const org = await db.prepare("SELECT id FROM orgs WHERE id = ?").bind(orgId).first<{ id: string }>();
  if (!org) return { ok: false, status: 404 };
  const role = await membershipRole(db, orgId, userId);
  if (!role || !roles.includes(role)) return { ok: false, status: 403 };
  return { ok: true, role };
}

// List my orgs.
app.get("/", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const rows = await c.env.DB.prepare(
    "SELECT o.id, o.slug, o.name, o.plan, m.role FROM orgs o JOIN memberships m ON m.org_id = o.id WHERE m.user_id = ? ORDER BY o.created_at",
  )
    .bind(user.id)
    .all();
  return c.json({ orgs: rows.results });
});

// Create org (caller becomes owner).
app.post("/", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const body = z.object({ name: z.string().min(1).max(120), slug: z.string().min(3).max(50) }).safeParse(await c.req.json().catch(() => null));
  if (!body.success || !slugRe.test(body.data.slug)) {
    return c.json({ error: { code: "bad_request", message: "Please type your company name." } }, 400);
  }
  const id = newId("org");
  const now = nowIso();
  try {
    await c.env.DB.prepare("INSERT INTO orgs (id, slug, name, plan, created_at) VALUES (?, ?, ?, 'free', ?)").bind(id, body.data.slug, body.data.name, now).run();
  } catch {
    return c.json({ error: { code: "conflict", message: "Slug already taken." } }, 409);
  }
  await c.env.DB.prepare("INSERT INTO memberships (org_id, user_id, role) VALUES (?, ?, 'owner')").bind(id, user.id).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId: id, actor: `user:${user.id}`, action: "org.create", detail: body.data.slug });
  return c.json({ id, slug: body.data.slug, name: body.data.name, plan: "free" }, 201);
});

// Agents (member+). Value metric = agents in production; plan-limited.
app.get("/:orgId/agents", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const gate = await needRole(c.env.DB, c.req.param("orgId"), user.id, ["owner", "member", "viewer"]);
  if (!gate.ok) return c.json({ error: { code: "forbidden", message: "No access to this org." } }, gate.status);
  const rows = await c.env.DB.prepare("SELECT id, name, status, created_at FROM agents WHERE org_id = ? ORDER BY created_at").bind(c.req.param("orgId")).all();
  return c.json({ agents: rows.results });
});

app.post("/:orgId/agents", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const gate = await needRole(c.env.DB, orgId, user.id, ["owner", "member"]);
  if (!gate.ok) return c.json({ error: { code: "forbidden", message: "No access to this org." } }, gate.status);
  const body = z.object({ name: z.string().min(1).max(120) }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Agent name required." } }, 400);
  const org = await c.env.DB.prepare("SELECT plan FROM orgs WHERE id = ?").bind(orgId).first<{ plan: string }>();
  const active = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM agents WHERE org_id = ? AND status = 'active'").bind(orgId).first<{ n: number }>();
  const allow = limitAllows(planOf(org?.plan), "agents", active?.n ?? 0);
  if (!allow.ok) return c.json({ error: { code: "plan_limit", message: allow.message } }, 402);
  const id = newId("agt");
  const now = nowIso();
  try {
    await c.env.DB.prepare("INSERT INTO agents (id, org_id, name, status, created_at) VALUES (?, ?, ?, 'active', ?)").bind(id, orgId, body.data.name, now).run();
  } catch {
    return c.json({ error: { code: "conflict", message: "Agent name already exists in this org." } }, 409);
  }
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "agent.create", detail: body.data.name });
  return c.json({ id, name: body.data.name, status: "active" }, 201);
});

app.patch("/:orgId/agents", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const gate = await needRole(c.env.DB, orgId, user.id, ["owner", "member"]);
  if (!gate.ok) return c.json({ error: { code: "forbidden", message: "No access to this org." } }, gate.status);
  const body = z.object({ id: z.string().min(1), status: z.enum(["active", "archived"]) }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Agent id and status required." } }, 400);
  const res = await c.env.DB.prepare("UPDATE agents SET status = ? WHERE id = ? AND org_id = ?").bind(body.data.status, body.data.id, orgId).run();
  if (res.meta.changes === 0) return c.json({ error: { code: "not_found", message: "Agent not found in this org." } }, 404);
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "agent.update", detail: `${body.data.id} -> ${body.data.status}` });
  return c.json({ ok: true });
});

export default app;
