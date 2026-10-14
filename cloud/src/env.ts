// Shared Worker bindings + env vars. Secrets (OAuth, SESSION_KEY,
// INBOX_SECRET_KEY, WITNESS_SIGNING_KEY, PADDLE_WEBHOOK_SECRET) come from
// `wrangler secret put` and are typed optional so unit tests can omit them.

export interface Env {
  DB: D1Database;
  ROOM: R2Bucket;
  WITNESS: DurableObjectNamespace;
  APP_ORIGIN: string;
  PUBLIC_WITNESS_URL: string;
  FOUNDER_USER_IDS?: string;
  GITHUB_CLIENT_ID?: string;
  GITHUB_CLIENT_SECRET?: string;
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
  SESSION_KEY?: string;
}
