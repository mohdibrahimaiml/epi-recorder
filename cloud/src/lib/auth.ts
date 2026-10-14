// Session cookies + tenant checks. Every org-scoped route goes through
// requireMembership: org A can never read B (tested in test/isolation).

import { newToken, sha256Hex } from "./crypto.ts";
import type { Env } from "../env.ts";

export const SESSION_COOKIE = "epi_session";
const SESSION_TTL_MS = 30 * 86_400_000;

export type Role = "owner" | "member" | "viewer";

export async function createSession(db: D1Database, userId: string): Promise<{ raw: string; expiresAt: string }> {
  const raw = newToken();
  const expiresAt = new Date(Date.now() + SESSION_TTL_MS).toISOString();
  await db
    .prepare("INSERT INTO sessions (id_hash, user_id, expires_at) VALUES (?, ?, ?)")
    .bind(await sha256Hex(raw), userId, expiresAt)
    .run();
  return { raw, expiresAt };
}

export function sessionCookie(raw: string, origin: string): string {
  const secure = origin.startsWith("https://") ? "; Secure" : "";
  return `${SESSION_COOKIE}=${raw}; HttpOnly${secure}; SameSite=Lax; Path=/; Max-Age=2592000`;
}

export function clearSessionCookie(): string {
  return `${SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0`;
}

function parseCookies(header: string | null): Record<string, string> {
  const out: Record<string, string> = {};
  if (!header) return out;
  for (const part of header.split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

export interface AuthedUser {
  id: string;
  email: string | null;
}

/** Cookie session -> user, or null. Share tokens and API keys never use cookies. */
export async function userFromRequest(db: D1Database, req: Request): Promise<AuthedUser | null> {
  const raw = parseCookies(req.headers.get("Cookie"))[SESSION_COOKIE];
  if (!raw) return null;
  const row = await db
    .prepare(
      "SELECT s.user_id, s.expires_at, u.email FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id_hash = ?",
    )
    .bind(await sha256Hex(raw))
    .first<{ user_id: string; expires_at: string; email: string | null }>();
  if (!row || row.expires_at <= new Date().toISOString()) return null;
  return { id: row.user_id, email: row.email };
}

export interface ApiKeyAuth {
  id: string;
  orgId: string;
  scopes: string[];
}

/** `Authorization: Bearer epik_…` -> key auth (CLI/gateway). Updates last_used_at. */
export async function keyFromRequest(db: D1Database, req: Request): Promise<ApiKeyAuth | null> {
  const h = req.headers.get("Authorization");
  if (!h || !h.startsWith("Bearer epik_")) return null;
  const row = await db
    .prepare("SELECT id, org_id, scopes FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL")
    .bind(await sha256Hex(h.slice("Bearer ".length)))
    .first<{ id: string; org_id: string; scopes: string }>();
  if (!row) return null;
  await db.prepare("UPDATE api_keys SET last_used_at = ? WHERE id = ?").bind(new Date().toISOString(), row.id).run();
  return { id: row.id, orgId: row.org_id, scopes: row.scopes.split(",").map((s) => s.trim()) };
}

/**
 * Tenant gate: returns the membership role or null. All org routes must
 * filter by the returned org — never trust a path param alone.
 */
export async function membershipRole(
  db: D1Database,
  orgId: string,
  userId: string,
): Promise<Role | null> {
  const row = await db
    .prepare("SELECT role FROM memberships WHERE org_id = ? AND user_id = ?")
    .bind(orgId, userId)
    .first<{ role: Role }>();
  return row?.role ?? null;
}

export function originAllowed(req: Request, env: Env): boolean {
  const origin = req.headers.get("Origin");
  if (!origin) return true; // CLI / curl have no Origin
  const allowed = new Set([env.APP_ORIGIN, "https://epilabs.org", "http://localhost:8787", "http://127.0.0.1:8787"]);
  return allowed.has(origin);
}
