// Retention purge (runs inside the daily cron): delete Evidence Room files
// past retention_until unless on legal hold. Audit-logged per file.

import type { Env } from "./env.ts";
import { nowIso } from "./lib/crypto.ts";
import { auditLog, d1AuditDb } from "./lib/audit.ts";

export interface PurgeSummary {
  examined: number;
  deleted: number;
}

export async function purgeExpiredArtifacts(env: Env, now: string = nowIso()): Promise<PurgeSummary> {
  const rows = await env.DB.prepare(
    "SELECT id, org_id, object_key FROM artifacts WHERE deleted_at IS NULL AND legal_hold = 0 AND retention_until <= ?",
  ).bind(now).all<{ id: string; org_id: string; object_key: string }>();
  const summary: PurgeSummary = { examined: (rows.results ?? []).length, deleted: 0 };
  for (const row of rows.results ?? []) {
    try {
      await env.ROOM.delete(row.object_key);
    } catch {
      continue; // R2 hiccup: retry tomorrow, keep the row.
    }
    await env.DB.prepare("UPDATE artifacts SET deleted_at = ? WHERE id = ?").bind(now, row.id).run();
    await auditLog(d1AuditDb(env.DB), { orgId: row.org_id, actor: "system:cron", action: "artifact.retention_delete", detail: row.id });
    summary.deleted++;
  }
  return summary;
}
