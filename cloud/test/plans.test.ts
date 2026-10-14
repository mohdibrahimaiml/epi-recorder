import { describe, expect, it } from "vitest";
import { limitAllows, planOf, retentionUntil, PLAN_LIMITS } from "../src/lib/plans.ts";

describe("plans (single source of truth)", () => {
  it("free tier matches the v2 proposal", () => {
    expect(PLAN_LIMITS.free).toEqual({ agents: 1, inboxes: 1, evidenceFiles: 50, retentionDays: 30, shareLinks: 1 });
  });
  it("unknown plans fall back to free", () => {
    expect(planOf("hosted")).toBe("free");
    expect(planOf(undefined)).toBe("free");
  });
  it("blocks at the limit with an upgrade hint, never deletes", () => {
    expect(limitAllows("free", "agents", 0)).toEqual({ ok: true });
    const r = limitAllows("free", "agents", 1);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.message).toMatch(/Upgrade/);
  });
  it("enterprise (custom) never blocks", () => {
    expect(limitAllows("enterprise", "agents", 100000)).toEqual({ ok: true });
  });
  it("retention math: free 30 days, partner 7 years", () => {
    expect(retentionUntil("free", "2026-01-01T00:00:00.000Z")).toBe("2026-01-31T00:00:00.000Z");
    expect(retentionUntil("design_partner", "2026-01-01T00:00:00.000Z")).toBe("2032-12-30T00:00:00.000Z");
  });
});
