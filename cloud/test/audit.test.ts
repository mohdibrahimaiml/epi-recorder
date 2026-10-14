import { describe, expect, it } from "vitest";
import { auditLog, type AuditDb } from "../src/lib/audit.ts";
import { sha256Hex } from "../src/lib/crypto.ts";

function memStore(): AuditDb & { rows: Array<{ prevHash: string; entryHash: string; detail: string; at: string }> } {
  const rows: Array<{ prevHash: string; entryHash: string; detail: string; at: string }> = [];
  return {
    rows,
    async getPrevHash() {
      return rows.length ? rows[rows.length - 1]!.entryHash : "GENESIS";
    },
    async insert(e) {
      rows.push({ prevHash: e.prevHash, entryHash: e.entryHash, detail: e.detail, at: e.at });
    },
  };
}

describe("hash-chained audit log", () => {
  it("links entries and recomputes", async () => {
    const store = memStore();
    const h1 = await auditLog(store, { orgId: "org_1", actor: "user:a", action: "org.create", detail: "acme" });
    const h2 = await auditLog(store, { orgId: "org_1", actor: "user:a", action: "agent.create", detail: "loan" });
    expect(store.rows).toHaveLength(2);
    expect(store.rows[0]!.prevHash).toBe("GENESIS");
    expect(store.rows[1]!.prevHash).toBe(h1);
    expect(h2).toBe(store.rows[1]!.entryHash);
    // Recompute the second link independently.
    const expect2 = await sha256Hex([h1, "org_1", "user:a", "agent.create", "loan", store.rows[1]!.at].join("|"));
    expect(h2).toBe(expect2);
  });
});
