import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { newId, newToken, nowIso, sha256Hex } from "../lib/crypto.ts";
import { membershipRole, userFromRequest } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";
import { checkRateLimit, d1CounterStore } from "../lib/ratelimit.ts";
import { limitAllows, planOf } from "../lib/plans.ts";

const app = new Hono<{ Bindings: Env }>();

const scopeSchema = z.object({
  agents: z.union([z.literal("all"), z.array(z.string().min(1)).max(100)]).default("all"),
  inboxes: z.union([z.literal("all"), z.array(z.string().min(1)).max(50)]).default("all"),
});

export type ShareScope = z.infer<typeof scopeSchema>;

function inScope<T extends { id: string }>(scope: "all" | string[], rows: T[]): T[] {
  if (scope === "all") return rows;
  const keep = new Set(scope);
  return rows.filter((r) => keep.has(r.id));
}

// Owner mints a trust link. Token shown ONCE (fragment-only, never logged).
app.post("/orgs/:orgId/share-links", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  const body = z.object({
    label: z.string().min(1).max(120),
    scope: scopeSchema.optional(),
    expires_at: z.string().min(1).optional(),
  }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Label required." } }, 400);
  const org = await c.env.DB.prepare("SELECT plan FROM orgs WHERE id = ?").bind(orgId).first<{ plan: string }>();
  if (!org) return c.json({ error: { code: "not_found", message: "Org not found." } }, 404);
  const active = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM share_links WHERE org_id = ? AND revoked_at IS NULL").bind(orgId).first<{ n: number }>();
  const allow = limitAllows(planOf(org.plan), "shareLinks", active?.n ?? 0);
  if (!allow.ok) return c.json({ error: { code: "plan_limit", message: allow.message } }, 402);
  const scope = body.data.scope ?? { agents: "all", inboxes: "all" };
  const expiresAt = body.data.expires_at ?? new Date(Date.now() + 90 * 86_400_000).toISOString();
  const id = newId("sh");
  const token = newToken();
  await c.env.DB.prepare(
    "INSERT INTO share_links (id, org_id, token_hash, label, scope, created_at, expires_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
  ).bind(id, orgId, await sha256Hex(token), body.data.label, JSON.stringify(scope), nowIso(), expiresAt).run();
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "share_link.create", detail: `${id} ${body.data.label}` });
  return c.json({ id, token, url: `/t/${id}#k=${token}` }, 201);
});

app.get("/orgs/:orgId/share-links", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  const rows = await c.env.DB.prepare(
    "SELECT id, label, scope, created_at, expires_at, revoked_at FROM share_links WHERE org_id = ? ORDER BY created_at",
  ).bind(orgId).all();
  return c.json({ links: rows.results });
});

app.delete("/orgs/:orgId/share-links/:linkId", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  if ((await membershipRole(c.env.DB, orgId, user.id)) !== "owner") {
    return c.json({ error: { code: "forbidden", message: "Owners only." } }, 403);
  }
  const res = await c.env.DB.prepare("UPDATE share_links SET revoked_at = ? WHERE id = ? AND org_id = ? AND revoked_at IS NULL")
    .bind(nowIso(), c.req.param("linkId"), orgId).run();
  if (res.meta.changes === 0) return c.json({ error: { code: "not_found", message: "Link not found." } }, 404);
  await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${user.id}`, action: "share_link.revoke", detail: c.req.param("linkId") });
  return c.json({ ok: true });
});

// Vendor dashboard: who actually opened / verified (human actions only).
app.get("/orgs/:orgId/share-links/:linkId/events", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const orgId = c.req.param("orgId");
  const role = await membershipRole(c.env.DB, orgId, user.id);
  if (!role) return c.json({ error: { code: "forbidden", message: "No access to this org." } }, 403);
  const link = await c.env.DB.prepare("SELECT id FROM share_links WHERE id = ? AND org_id = ?").bind(c.req.param("linkId"), orgId).first<{ id: string }>();
  if (!link) return c.json({ error: { code: "not_found", message: "Link not found." } }, 404);
  const rows = await c.env.DB.prepare("SELECT kind, detail, at FROM trust_events WHERE share_link_id = ? ORDER BY id ASC LIMIT 500").bind(link.id).all();
  return c.json({ events: rows.results });
});

export interface TrustLink {
  id: string;
  org_id: string;
  label: string;
  scope: ShareScope;
  expires_at: string;
}

/** Resolve a share token (header only, never URL). Null when invalid/expired/revoked. */
export async function trustLinkFromRequest(db: D1Database, req: Request): Promise<TrustLink | null> {
  const token = req.headers.get("X-EPI-Share-Token");
  if (!token || token.length > 256) return null;
  const row = await db.prepare(
    "SELECT id, org_id, label, scope, expires_at, revoked_at FROM share_links WHERE token_hash = ?",
  ).bind(await sha256Hex(token)).first<{
    id: string; org_id: string; label: string; scope: string; expires_at: string; revoked_at: string | null;
  }>();
  if (!row || row.revoked_at || row.expires_at <= nowIso()) return null;
  const scope = scopeSchema.safeParse(JSON.parse(row.scope));
  if (!scope.success) return null;
  return { id: row.id, org_id: row.org_id, label: row.label, scope: scope.data, expires_at: row.expires_at };
}

export interface TrustDoc {
  vendor: string;
  link_label: string;
  agents: Array<{ id: string; name: string; status: string }>;
  inboxes: Array<{
    id: string; label: string; total_witnessed: number;
    d30: number; d90: number; last_day: string | null; anchored: boolean;
    awaiting_checkpoint: boolean;
  }>;
  artifacts: Array<Record<string, unknown>>;
  keys: Array<{ fingerprint: string; label: string | null; valid_from: string; revoked_at: string | null }>;
  note: string;
}

function cutoff(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
}

export async function buildTrustDoc(db: D1Database, env: Env, link: TrustLink): Promise<TrustDoc> {
  const org = await db.prepare("SELECT name FROM orgs WHERE id = ?").bind(link.org_id).first<{ name: string }>();
  const agentRows = await db.prepare("SELECT id, name, status FROM agents WHERE org_id = ? ORDER BY created_at").bind(link.org_id).all<{ id: string; name: string; status: string }>();
  const inboxRows = await db.prepare("SELECT id, customer_label, closed_at FROM inboxes WHERE org_id = ? ORDER BY created_at").bind(link.org_id).all<{ id: string; customer_label: string; closed_at: string | null }>();
  const agents = inScope(link.scope.agents, (agentRows.results ?? []) as Array<{ id: string; name: string; status: string }>);
  const inboxesAll = (inboxRows.results ?? []) as Array<{ id: string; customer_label: string; closed_at: string | null }>;
  const inboxes = inScope(link.scope.inboxes, inboxesAll.map((r) => ({ id: r.id }))).map((s) => inboxesAll.find((r) => r.id === s.id)!);

  const out: TrustDoc["inboxes"] = [];
  for (const inbox of inboxes) {
    const cps = await db.prepare(
      "SELECT day, count, head_hash, signed_at, rekor_uuid FROM checkpoints WHERE inbox_id = ? AND day >= ? ORDER BY day ASC",
    ).bind(inbox.id, cutoff(90)).all<{ day: string; count: number; head_hash: string; signed_at: string; rekor_uuid: string | null }>();
    const rows = cps.results ?? [];
    const d30 = rows.filter((r) => r.day >= cutoff(30)).reduce((n, r) => n + r.count, 0);
    const d90 = rows.reduce((n, r) => n + r.count, 0);
    let total = d90;
    let anchored = rows.length > 0 && rows.every((r) => !!r.rekor_uuid);
    try {
      const stub = env.WITNESS.get(env.WITNESS.idFromName(inbox.id));
      const info = (await (await stub.fetch("https://inbox/info")).json()) as { count: number; head_hash: string };
      total = Math.max(total, info.count);
    } catch {
      // DO unreachable: checkpoint sums still stand.
    }
    out.push({
      id: inbox.id, label: inbox.customer_label, total_witnessed: total,
      d30, d90, last_day: rows.length ? rows[rows.length - 1]!.day : null, anchored,
      // Entries exist in the log but no signed checkpoint covers them yet
      // (e.g. signing keys unconfigured): say so instead of showing 0.
      awaiting_checkpoint: total > 0 && rows.length === 0,
    });
  }

  const artRows = await db.prepare(
    "SELECT id, claimed_sha256, size_bytes, workflow_id, goal, sealed_at, key_fingerprint, signature_check, witness_status, reason FROM artifacts WHERE org_id = ? AND deleted_at IS NULL ORDER BY uploaded_at DESC LIMIT 200",
  ).bind(link.org_id).all();
  const keyRows = await db.prepare("SELECT fingerprint, label, valid_from, revoked_at FROM org_keys WHERE org_id = ? ORDER BY valid_from").bind(link.org_id).all<{
    fingerprint: string; label: string | null; valid_from: string; revoked_at: string | null;
  }>();

  return {
    vendor: org?.name ?? "Vendor",
    link_label: link.label,
    agents: agents.map((a) => ({ id: a.id, name: a.name, status: a.status })),
    inboxes: out,
    artifacts: (artRows.results ?? []) as Array<Record<string, unknown>>,
    keys: (keyRows.results ?? []) as Array<{ fingerprint: string; label: string | null; valid_from: string; revoked_at: string | null }>,
    note: "Counts come from signed daily checkpoints; verification runs in your browser, never on our server.",
  };
}

// Reviewer-facing trust data. Token in the X-EPI-Share-Token header only.
app.get("/trust/:slug", async (c) => {
  const link = await trustLinkFromRequest(c.env.DB, c.req.raw);
  if (!link || link.id !== c.req.param("slug")) {
    return c.json({ error: { code: "not_found", message: "This link is invalid, expired, or revoked." } }, 404);
  }
  return c.json(await buildTrustDoc(c.env.DB, c.env, link));
});

const eventSchema = z.object({
  kind: z.enum(["opened", "verified_file", "downloaded_pack", "downloaded_witness"]),
  detail: z.string().max(300).optional(),
});

// Human actions only: the page sends these on clicks, never on load.
app.post("/trust/:slug/events", async (c) => {
  const link = await trustLinkFromRequest(c.env.DB, c.req.raw);
  if (!link || link.id !== c.req.param("slug")) {
    return c.json({ error: { code: "not_found", message: "This link is invalid, expired, or revoked." } }, 404);
  }
  const body = eventSchema.safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "Known event kind required." } }, 400);
  const limited = await checkRateLimit(d1CounterStore(c.env.DB), `trust-events:${link.id}`, 60, 60);
  if (!limited.ok) return c.json({ error: { code: "rate_limited", message: "Slow down." } }, 429);
  await c.env.DB.prepare("INSERT INTO trust_events (share_link_id, kind, detail, at) VALUES (?, ?, ?, ?)")
    .bind(link.id, body.data.kind, body.data.detail ?? null, nowIso()).run();
  return c.json({ ok: true });
});

export default app;
