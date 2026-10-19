import type { Env } from "../env.ts";
import { newId, newToken, nowIso } from "./crypto.ts";
import { auditLog, d1AuditDb } from "./audit.ts";
import { limitAllows, planOf, PLAN_LIMITS, type PlanId } from "./plans.ts";
import { openSecret, sealSecret } from "./secretbox.ts";

export type EnsureCustomerResult =
  | {
      ok: true;
      agentId: string;
      inboxId: string;
      url: string;
      secret: string;
      created: boolean;
      /** Canonical customer name (existing spelling wins over what was typed). */
      label: string;
    }
  | { ok: false; status: 400 | 402 | 403 | 404 | 409 | 503; code: string; message: string };

function fail(status: 400 | 402 | 403 | 404 | 409 | 503, code: string, message: string): EnsureCustomerResult {
  return { ok: false, status, code, message };
}

/**
 * Customer words for the "adding one more customer" wall. The person
 * clicking only knows customers; "agents" is an internal name for the
 * recorder identity each customer gets, so it never appears here.
 */
function customerLimitMessage(plan: PlanId, metric: "agents" | "inboxes"): string {
  const max = PLAN_LIMITS[plan][metric];
  const n = max === null ? "unlimited" : max;
  const s = max === 1 ? "" : "s";
  return `Your ${plan} plan includes ${n} customer${s}. Upgrade to add more — your data stays.`;
}

/** Recorder name for a customer (dashboard convention: agent name == customer label). */
export function agentNameForCustomer(customerLabel: string): string {
  return customerLabel;
}

/**
 * Find-or-create the recorder identity + witness inbox for one customer.
 *
 * Agent creation is allowed for owners and members (mirrors POST /agents);
 * inbox creation is owners-only (mirrors POST /inboxes), because it mints a
 * new shared secret. Selecting existing rows needs no privilege beyond what
 * the caller already proved to reach this helper.
 */
export async function ensureCustomerInbox(
  db: D1Database,
  env: Env,
  orgId: string,
  customerLabel: string,
  actor: string,
  opts: { allowCreateInbox: boolean; allowCreateAgent: boolean },
): Promise<EnsureCustomerResult> {
  // "test bank " and "Test  Bank" are the same customer as "Test Bank":
  // collapse whitespace and match case-insensitively, keeping the spelling
  // the customer was first created with.
  let label = String(customerLabel ?? "").trim().replace(/\s+/g, " ");
  if (!label || label.length > 120) {
    return fail(400, "bad_request", "A customer name (1-120 characters) is required.");
  }
  const org = await db.prepare("SELECT plan FROM orgs WHERE id = ?").bind(orgId).first<{ plan: string }>();
  if (!org) return fail(404, "not_found", "Org not found.");
  if (!env.INBOX_SECRET_KEY) {
    return fail(503, "not_configured", "Inbox encryption is not configured yet.");
  }

  let agent = await db.prepare("SELECT id, name, status FROM agents WHERE org_id = ? AND lower(name) = lower(?)")
    .bind(orgId, agentNameForCustomer(label))
    .first<{ id: string; name: string; status?: string }>();
  if (agent) label = agent.name;
  if (agent && agent.status === "archived") {
    // A customer that was closed earlier and is being used again: it counts
    // toward the plan once more.
    if (!opts.allowCreateAgent) {
      return fail(403, "forbidden", `"${label}" was closed. Ask a workspace owner to reopen it.`);
    }
    const active = await db.prepare("SELECT COUNT(*) AS n FROM agents WHERE org_id = ? AND status = 'active'").bind(orgId).first<{ n: number }>();
    const allow = limitAllows(planOf(org.plan), "agents", active?.n ?? 0);
    if (!allow.ok) return fail(402, "plan_limit", customerLimitMessage(planOf(org.plan), "agents"));
    await db.prepare("UPDATE agents SET status = 'active' WHERE id = ?").bind(agent.id).run();
  }
  if (!agent) {
    if (!opts.allowCreateAgent) {
      return fail(403, "forbidden", `Unknown customer "${label}". Ask a workspace owner to add it first.`);
    }
    const active = await db.prepare("SELECT COUNT(*) AS n FROM agents WHERE org_id = ? AND status = 'active'").bind(orgId).first<{ n: number }>();
    const agentAllow = limitAllows(planOf(org.plan), "agents", active?.n ?? 0);
    if (!agentAllow.ok) return fail(402, "plan_limit", customerLimitMessage(planOf(org.plan), "agents"));
    const agentId = newId("agt");
    try {
      await db.prepare("INSERT INTO agents (id, org_id, name, status, created_at) VALUES (?, ?, ?, 'active', ?)")
        .bind(agentId, orgId, agentNameForCustomer(label), nowIso())
        .run();
    } catch {
      // Lost a race with another creator: fall back to whatever exists now.
      agent = await db.prepare("SELECT id, name FROM agents WHERE org_id = ? AND lower(name) = lower(?)")
        .bind(orgId, agentNameForCustomer(label))
        .first<{ id: string; name: string }>();
      if (!agent) return fail(409, "conflict", "Agent name already exists in this org.");
    }
    if (!agent) {
      agent = { id: agentId, name: label };
      await auditLog(d1AuditDb(db), { orgId, actor, action: "agent.create", detail: label });
    }
  }

  const row = await db.prepare("SELECT id, hmac_secret_enc FROM inboxes WHERE org_id = ? AND lower(customer_label) = lower(?) AND closed_at IS NULL")
    .bind(orgId, label)
    .first<{ id: string; hmac_secret_enc: string }>();
  if (row) {
    const secret = await openSecret(env.INBOX_SECRET_KEY, row.hmac_secret_enc);
    return {
      ok: true, agentId: agent.id, inboxId: row.id,
      url: `${env.PUBLIC_WITNESS_URL}/w/${row.id}`, secret, created: false, label,
    };
  }
  if (!opts.allowCreateInbox) {
    return fail(403, "forbidden", `Unknown customer "${label}". Ask a workspace owner to add it first.`);
  }
  const open = await db.prepare("SELECT COUNT(*) AS n FROM inboxes WHERE org_id = ? AND closed_at IS NULL").bind(orgId).first<{ n: number }>();
  const inboxAllow = limitAllows(planOf(org.plan), "inboxes", open?.n ?? 0);
  if (!inboxAllow.ok) return fail(402, "plan_limit", inboxAllow.message);
  const id = newId("inb");
  const secret = newToken();
  await db.prepare("INSERT INTO inboxes (id, org_id, customer_label, hmac_secret_enc, created_at, closed_at) VALUES (?, ?, ?, ?, ?, NULL)")
    .bind(id, orgId, label, await sealSecret(env.INBOX_SECRET_KEY, secret), nowIso())
    .run();
  await auditLog(d1AuditDb(db), { orgId, actor, action: "inbox.create", detail: `${id} for ${label}` });
  return {
    ok: true, agentId: agent.id, inboxId: id,
    url: `${env.PUBLIC_WITNESS_URL}/w/${id}`, secret, created: true, label,
  };
}
