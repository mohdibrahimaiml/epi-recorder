// Hash-chained audit log. Every mutating route appends one entry; the
// chain makes silent edits detectable (recompute to verify).

import { nowIso, sha256Hex } from "./crypto.ts";

export interface AuditDb {
  getPrevHash(orgId: string | null): Promise<string>;
  insert(entry: {
    orgId: string | null;
    actor: string;
    action: string;
    detail: string;
    at: string;
    prevHash: string;
    entryHash: string;
  }): Promise<void>;
}

export function d1AuditDb(db: D1Database): AuditDb {
  return {
    async getPrevHash(orgId) {
      const row = await db
        .prepare("SELECT entry_hash FROM audit_log WHERE org_id IS ? ORDER BY seq DESC LIMIT 1")
        .bind(orgId)
        .first<{ entry_hash: string }>();
      return row?.entry_hash ?? "GENESIS";
    },
    async insert(e) {
      await db
        .prepare(
          "INSERT INTO audit_log (org_id, actor, action, detail, at, prev_hash, entry_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(e.orgId, e.actor, e.action, e.detail, e.at, e.prevHash, e.entryHash)
        .run();
    },
  };
}

export async function auditLog(
  store: AuditDb,
  opts: { orgId: string | null; actor: string; action: string; detail: string },
): Promise<string> {
  const at = nowIso();
  const prevHash = await store.getPrevHash(opts.orgId);
  const entryHash = await sha256Hex(
    [prevHash, opts.orgId ?? "-", opts.actor, opts.action, opts.detail, at].join("|"),
  );
  await store.insert({ ...opts, at, prevHash, entryHash });
  return entryHash;
}
