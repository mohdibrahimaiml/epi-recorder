import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { userFromRequest } from "../lib/auth.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";
import { esc, page } from "../ui.ts";
import type { PlanId } from "../lib/plans.ts";

const app = new Hono<{ Bindings: Env }>();

async function requireFounder(
  db: D1Database, req: Request, env: Env,
): Promise<{ ok: true; userId: string; email: string | null } | { ok: false; status: 401 | 403 }> {
  const user = await userFromRequest(db, req);
  if (!user) return { ok: false, status: 401 };
  const founders = (env.FOUNDER_USER_IDS ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!founders.includes(user.id)) return { ok: false, status: 403 };
  // The id alone is not enough: only a verified login counts. A user row
  // can exist with someone else's address unverified, so an allowlist of
  // bare ids would hand founder power to whoever claims one.
  const row = await db.prepare("SELECT email_verified FROM users WHERE id = ?").bind(user.id)
    .first<{ email_verified: number }>();
  if (!row || !row.email_verified) return { ok: false, status: 403 };
  return { ok: true, userId: user.id, email: user.email };
}

function founderDenied(status: 401 | 403) {
  return status === 401
    ? { code: "unauthorized", message: "Sign in first." }
    : { code: "forbidden", message: "Founder only." };
}

// Founder-only usage vs free limits (allowlisted user ids in FOUNDER_USER_IDS).
app.get("/usage", async (c) => {
  const f = await requireFounder(c.env.DB, c.req.raw, c.env);
  if (!f.ok) return c.json({ error: founderDenied(f.status) }, f.status);
  const count = async (sql: string) =>
    (await c.env.DB.prepare(sql).first<{ n: number }>())?.n ?? 0;
  return c.json({
    limits: {
      workers_requests_per_day: 100000,
      workers_cpu_ms_per_request: 10,
      d1_rows_read_per_day: 5000000,
      d1_rows_written_per_day: 100000,
      d1_storage_gb: 5,
      durable_object_requests_per_day: 100000,
      r2_storage_gb_month: 10,
      r2_class_a_ops_per_month: 1000000,
      r2_class_b_ops_per_month: 10000000,
      alert_at_percent: 70,
    },
    usage: {
      orgs: await count("SELECT COUNT(*) AS n FROM orgs"),
      users: await count("SELECT COUNT(*) AS n FROM users"),
      active_api_keys: await count("SELECT COUNT(*) AS n FROM api_keys WHERE revoked_at IS NULL"),
      agents: await count("SELECT COUNT(*) AS n FROM agents WHERE status = 'active'"),
      inboxes: await count("SELECT COUNT(*) AS n FROM inboxes WHERE closed_at IS NULL"),
      artifacts: await count("SELECT COUNT(*) AS n FROM artifacts WHERE deleted_at IS NULL"),
    },
  });
});

const planSchema = z.enum(["free", "design_partner", "startup", "growth", "enterprise"]);

// Founder-only workspace list: name, plan, owner email, usage. Backs the
// /admin page and lets the founder change a plan without touching D1.
app.get("/orgs", async (c) => {
  const f = await requireFounder(c.env.DB, c.req.raw, c.env);
  if (!f.ok) return c.json({ error: founderDenied(f.status) }, f.status);
  const rows = await c.env.DB.prepare("SELECT id, slug, name, plan FROM orgs ORDER BY created_at").all<{
    id: string; slug: string; name: string; plan: string;
  }>();
  const orgs = [];
  for (const o of rows.results ?? []) {
    const owner = await c.env.DB.prepare("SELECT user_id FROM memberships WHERE org_id = ? AND role = ? ORDER BY user_id LIMIT 1")
      .bind(o.id, "owner").first<{ user_id: string }>();
    const ownerRow = owner
      ? await c.env.DB.prepare("SELECT email FROM users WHERE id = ?").bind(owner.user_id).first<{ email: string | null }>()
      : null;
    const cust = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM inboxes WHERE org_id = ? AND closed_at IS NULL").bind(o.id).first<{ n: number }>();
    const links = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM share_links WHERE org_id = ? AND revoked_at IS NULL").bind(o.id).first<{ n: number }>();
    const files = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM artifacts WHERE org_id = ? AND deleted_at IS NULL").bind(o.id).first<{ n: number }>();
    orgs.push({
      id: o.id, slug: o.slug, name: o.name, plan: o.plan,
      owner_email: ownerRow?.email ?? null,
      usage: { customers: cust?.n ?? 0, shareLinks: links?.n ?? 0, evidenceFiles: files?.n ?? 0 },
    });
  }
  return c.json({ orgs });
});

// Founder-only plan change. Audited; the previous plan is in the detail.
app.post("/orgs/:orgId/plan", async (c) => {
  const f = await requireFounder(c.env.DB, c.req.raw, c.env);
  if (!f.ok) return c.json({ error: founderDenied(f.status) }, f.status);
  const body = z.object({ plan: planSchema }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) {
    return c.json({ error: { code: "bad_request", message: "plan must be free, design_partner, startup, growth or enterprise." } }, 400);
  }
  const orgId = c.req.param("orgId");
  const row = await c.env.DB.prepare("SELECT plan FROM orgs WHERE id = ?").bind(orgId).first<{ plan: string }>();
  if (!row) return c.json({ error: { code: "not_found", message: "Workspace not found." } }, 404);
  const next = body.data.plan as PlanId;
  if (row.plan !== next) {
    await c.env.DB.prepare("UPDATE orgs SET plan = ? WHERE id = ?").bind(next, orgId).run();
    await auditLog(d1AuditDb(c.env.DB), { orgId, actor: `user:${f.userId}`, action: "org.plan", detail: `${orgId} ${row.plan} -> ${next}` });
  }
  return c.json({ id: orgId, plan: next });
});

// Founder-only page: every workspace, owner, usage, and a plan picker.
// Same origin + session cookie; state changes go through the endpoints above.
app.get("/", async (c) => {
  const f = await requireFounder(c.env.DB, c.req.raw, c.env);
  if (!f.ok) {
    return c.html(
      page("Founder admin — EPI Cloud", `<p class="err">Founder only. Sign in as the founder to manage workspace plans.</p>`),
      f.status as 401 | 403,
    );
  }
  const script = [
    `function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(ch){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];});};`,
    `var PLANS=["free","design_partner","startup","growth","enterprise"];`,
    `function row(o){var opts=PLANS.map(function(p){return '<option value="'+p+'"'+(p===o.plan?" selected":"")+'>'+p+'</option>';}).join("");var u=o.usage||{};return '<tr><td>'+esc(o.name)+'<div class="small mut">'+esc(o.id)+'</div></td><td>'+esc(o.owner_email||"—")+'</td><td class="small">'+esc(u.customers||0)+' customers · '+esc(u.shareLinks||0)+' links · '+esc(u.evidenceFiles||0)+' runs</td><td><select data-plan="'+esc(o.id)+'">'+opts+'</select> <button type="button" class="btn btn-sec" data-save="'+esc(o.id)+'">Save</button></td><td class="small" data-msg="'+esc(o.id)+'"></td></tr>';}`,
    `function load(){fetch("/admin/orgs",{credentials:"same-origin"}).then(function(r){return r.json().then(function(j){return {ok:r.ok,status:r.status,j:j};});}).then(function(x){var el=document.getElementById("rows");if(!x.ok){el.innerHTML='<tr><td colspan="5">Failed: '+esc((x.j&&x.j.error&&x.j.error.message)||("HTTP "+x.status))+'</td></tr>';return;}el.innerHTML=(x.j.orgs||[]).map(row).join("");el.querySelectorAll("button[data-save]").forEach(function(b){b.onclick=function(){var id=b.getAttribute("data-save");var sel=el.querySelector('select[data-plan="'+id+'"]');var cell=el.querySelector('[data-msg="'+id+'"]');cell.textContent="Saving…";fetch("/admin/orgs/"+encodeURIComponent(id)+"/plan",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({plan:sel.value})}).then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});}).then(function(y){cell.textContent=y.ok?("Plan: "+y.j.plan):("Failed: "+((y.j&&y.j.error&&y.j.error.message)||"unknown"));});};});});}`,
    `load();`,
  ].join("\n");
  return c.html(page(
    "Founder admin — EPI Cloud",
    `<span class="tag">Founder only</span><h1>Workspaces</h1>` +
    `<p class="small mut">Signed in as <strong>${esc(f.email ?? f.userId)}</strong>.</p>` +
    `<p class="lede">Change a workspace's plan here instead of the database. Every change is audited.</p>` +
    `<div class="twrap"><table class="tbl"><thead><tr><th>Workspace</th><th>Owner</th><th>Usage</th><th>Plan</th><th></th></tr></thead><tbody id="rows"><tr><td colspan="5">Loading…</td></tr></tbody></table></div>`,
    { script },
  ));
});

export default app;
