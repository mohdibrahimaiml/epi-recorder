import { describe, expect, it } from "vitest";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function migrationFiles(): string[] {
  return readdirSync(join(root, "migrations"))
    .filter((f) => f.endsWith(".sql"))
    .sort()
    .map((f) => join(root, "migrations", f));
}

const TABLES = [
  "orgs", "users", "identities", "memberships", "invites", "sessions",
  "api_keys", "agents", "inboxes", "checkpoints", "artifacts", "org_keys",
  "share_links", "trust_events", "storage_targets", "audit_log", "rate_counters",
];

function openDb(): DatabaseSync {
  const db = new DatabaseSync(":memory:");
  for (const file of migrationFiles()) db.exec(readFileSync(file, "utf8"));
  return db;
}

describe("0001_init.sql", () => {
  it("creates every table from the v2 data model", () => {
    const db = openDb();
    const names = new Set(
      (db.prepare("SELECT name FROM sqlite_master WHERE type = 'table'").all() as Array<{ name: string }>).map((r) => r.name),
    );
    for (const t of TABLES) expect(names.has(t), `missing table ${t}`).toBe(true);
    db.close();
  });

  it("enforces tenant-critical constraints (unique hash, event kinds)", () => {
    const db = openDb();
    db.prepare("INSERT INTO orgs (id, slug, name, plan, created_at) VALUES ('o1','acme','Acme','free','t')").run();
    db.prepare(
      "INSERT INTO artifacts (id, org_id, claimed_sha256, claimed_crc32, size_bytes, manifest_json, signature_check, witness_status, object_key, uploaded_at, retention_until) VALUES ('a1','o1','abc',1,10,'{}','valid','witnessed','k','t','t')",
    ).run();
    // Same sha twice in one org is a conflict (dedupe key).
    expect(() =>
      db.prepare(
        "INSERT INTO artifacts (id, org_id, claimed_sha256, claimed_crc32, size_bytes, manifest_json, signature_check, witness_status, object_key, uploaded_at, retention_until) VALUES ('a2','o1','abc',1,10,'{}','valid','witnessed','k2','t','t')",
      ).run(),
    ).toThrow();
    // Unknown trust event kinds are rejected.
    expect(() => db.prepare("INSERT INTO trust_events (share_link_id, kind, at) VALUES ('s','viewed','t')").run()).toThrow();
    db.prepare("INSERT INTO trust_events (share_link_id, kind, at) VALUES ('s','opened','t')").run();
    db.close();
  });

  it("stores an audit entry with a verifiable chain link", () => {
    const db = openDb();
    db.prepare("INSERT INTO audit_log (org_id, actor, action, detail, at, prev_hash, entry_hash) VALUES ('o1','user:a','org.create','acme','t','GENESIS','H1')").run();
    const row = db.prepare("SELECT prev_hash, entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1").get() as { prev_hash: string; entry_hash: string };
    expect(row.prev_hash).toBe("GENESIS");
    expect(row.entry_hash).toBe("H1");
    db.close();
  });

  it("0002 adds vendor-reported object_lock to storage_targets", () => {
    const db = openDb();
    db.prepare("INSERT INTO storage_targets (org_id, kind, endpoint, bucket) VALUES ('o1','s3','https://s3.example','b')").run();
    const row = db.prepare("SELECT object_lock FROM storage_targets WHERE org_id = 'o1'").get() as { object_lock: string };
    expect(row.object_lock).toBe("unknown");
    db.close();
  });
});
