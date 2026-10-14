import { Hono } from "hono";
import type { Env } from "../env.ts";
import { userFromRequest } from "../lib/auth.ts";

const app = new Hono<{ Bindings: Env }>();

// Founder-only usage vs free limits (allowlisted user ids in FOUNDER_USER_IDS).
app.get("/usage", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  const founders = (c.env.FOUNDER_USER_IDS ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!user || !founders.includes(user.id)) {
    return c.json({ error: { code: "forbidden", message: "Founder only." } }, 403);
  }
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

export default app;
