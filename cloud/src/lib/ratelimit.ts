// Fixed-window rate limits backed by D1 `rate_counters` (Workers have no
// shared in-memory state). One row per key; cheap single-row read + write.
// Limits (§6.1): login 10/min/IP, witness 600/min/inbox, push 60/min/key.

import { nowIso } from "./crypto.ts";

export interface CounterStore {
  get(key: string): Promise<{ count: number; window_expires_at: string } | null>;
  put(key: string, count: number, windowExpiresAt: string): Promise<void>;
}

export function d1CounterStore(db: D1Database): CounterStore {
  return {
    async get(key) {
      return db
        .prepare("SELECT count, window_expires_at FROM rate_counters WHERE key = ?")
        .bind(key)
        .first<{ count: number; window_expires_at: string }>();
    },
    async put(key, count, windowExpiresAt) {
      await db
        .prepare(
          "INSERT INTO rate_counters (key, count, window_expires_at) VALUES (?, ?, ?) " +
            "ON CONFLICT(key) DO UPDATE SET count = excluded.count, window_expires_at = excluded.window_expires_at",
        )
        .bind(key, count, windowExpiresAt)
        .run();
    },
  };
}

export async function checkRateLimit(
  store: CounterStore,
  key: string,
  limit: number,
  windowSec: number,
  nowMs = Date.now(),
): Promise<{ ok: true } | { ok: false; retryAfterSec: number }> {
  const row = await store.get(key);
  const now = new Date(nowMs).toISOString();
  if (!row || row.window_expires_at <= now) {
    await store.put(key, 1, new Date(nowMs + windowSec * 1000).toISOString());
    return { ok: true };
  }
  if (row.count < limit) {
    await store.put(key, row.count + 1, row.window_expires_at);
    return { ok: true };
  }
  const retryAfterSec = Math.max(1, Math.ceil((Date.parse(row.window_expires_at) - nowMs) / 1000));
  return { ok: false, retryAfterSec };
}

export function clientIp(req: Request): string {
  return req.headers.get("CF-Connecting-IP") ?? req.headers.get("X-Forwarded-For")?.split(",")[0]?.trim() ?? "unknown";
}

export { nowIso };
