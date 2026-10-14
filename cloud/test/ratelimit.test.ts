import { describe, expect, it } from "vitest";
import { checkRateLimit, type CounterStore } from "../src/lib/ratelimit.ts";

function memCounters(): CounterStore & { rows: Map<string, { count: number; window_expires_at: string }> } {
  const rows = new Map<string, { count: number; window_expires_at: string }>();
  return {
    rows,
    async get(key) {
      return rows.get(key) ?? null;
    },
    async put(key, count, windowExpiresAt) {
      rows.set(key, { count, window_expires_at: windowExpiresAt });
    },
  };
}

describe("fixed-window rate limits", () => {
  it("allows up to the limit, then blocks with retry-after", async () => {
    const s = memCounters();
    const t0 = Date.parse("2026-01-01T00:00:00.000Z");
    for (let i = 0; i < 10; i++) expect(await checkRateLimit(s, "login:1.2.3.4", 10, 60, t0 + i * 100)).toEqual({ ok: true });
    const blocked = await checkRateLimit(s, "login:1.2.3.4", 10, 60, t0 + 2000);
    expect(blocked.ok).toBe(false);
    if (!blocked.ok) expect(blocked.retryAfterSec).toBeGreaterThan(0);
  });
  it("resets when the window expires", async () => {
    const s = memCounters();
    const t0 = Date.parse("2026-01-01T00:00:00.000Z");
    await checkRateLimit(s, "push:key1", 1, 60, t0);
    expect((await checkRateLimit(s, "push:key1", 1, 60, t0 + 1000)).ok).toBe(false);
    expect(await checkRateLimit(s, "push:key1", 1, 60, t0 + 61_000)).toEqual({ ok: true });
  });
});
