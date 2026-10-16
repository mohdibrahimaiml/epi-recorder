import { Hono } from "hono";
import type { Env } from "./env.ts";
import { originAllowed, userFromRequest } from "./lib/auth.ts";
import auth from "./routes/auth.ts";
import orgs from "./routes/orgs.ts";
import invites from "./routes/invites.ts";
import keys from "./routes/keys.ts";
import admin from "./routes/admin.ts";
import inboxes from "./routes/inboxes.ts";
import shares from "./routes/shares.ts";
import artifacts from "./routes/artifacts.ts";
import storage from "./routes/storage.ts";
import witness, { witnessKeys } from "./routes/witness.ts";
import { runCheckpointCron } from "./cron.ts";
import { purgeExpiredArtifacts } from "./retention.ts";

export { WitnessInbox } from "./do/witness.ts";

const app = new Hono<{ Bindings: Env }>();

// Security headers on every response; API is never indexed.
app.use("*", async (c, next) => {
  await next();
  c.header("X-Content-Type-Options", "nosniff");
  c.header("X-Frame-Options", "DENY");
  c.header("Referrer-Policy", "no-referrer");
  c.header("X-Robots-Tag", "noindex");
});

// CSRF: cookie-authed state changes must carry an allowed Origin.
app.use("*", async (c, next) => {
  const method = c.req.method;
  if ((method === "POST" || method === "PATCH" || method === "PUT" || method === "DELETE") && c.req.header("Cookie")) {
    if (!originAllowed(c.req.raw, c.env)) {
      return c.json({ error: { code: "bad_origin", message: "Origin not allowed." } }, 403);
    }
  }
  return next();
});

app.onError((err, c) => {
  console.error(err);
  return c.json({ error: { code: "internal", message: "Unexpected error." } }, 500);
});

app.get("/health", (c) => c.json({ ok: true, service: "epi-cloud", m: 1 }));
app.route("/auth", auth);
app.route("/v1/orgs", orgs);
app.route("/v1", invites);
app.route("/v1", keys);
app.route("/v1", inboxes);
app.route("/v1", shares);
app.route("/v1", artifacts);
app.route("/v1", storage);
app.route("/admin", admin);
app.route("/w", witness);
app.get("/.well-known/epi-witness-key.json", (c) => c.json(witnessKeys(c.env)));

// Front door (normal users never touch raw /auth URLs). Static HTML, no JS,
// no events, no signal: scanners and link previews create nothing.
app.get("/", async (c) => {
  let email: string | null = null;
  try {
    email = (await userFromRequest(c.env.DB, c.req.raw))?.email ?? null;
  } catch {
    email = null;
  }
  const esc = (s: string) =>
    s.replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]!,
    );
  const account = email
    ? `<p>Signed in as <strong>${esc(email)}</strong>.</p>
       <form method="post" action="/auth/logout"><button type="submit">Sign out</button></form>
       <p>Next: connect your recorder with <code>epi cloud login</code>, or open a vendor trust link you received.</p>`
    : `<p><a class="btn" href="/auth/github">Sign in with GitHub</a></p>` +
      (c.env.GOOGLE_CLIENT_ID ? ` <p><a class="btn" href="/auth/google">Sign in with Google</a></p>` : ``) +
      `<p>One account signs every recorder, inbox, and trust page.</p>`;
  return c.html(
    `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">` +
      `<meta name="viewport" content="width=device-width,initial-scale=1">` +
      `<meta name="robots" content="noindex,nofollow">` +
      `<title>EPI Cloud — sealed evidence for AI runs</title>` +
      `<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem;line-height:1.6}` +
      `.btn{display:inline-block;background:#111;color:#fff;padding:.6rem 1.2rem;border-radius:.4rem;text-decoration:none}` +
      `button{font:inherit;padding:.4rem 1rem;cursor:pointer}code{background:#f0f0f0;padding:.1rem .3rem}</style></head>` +
      `<body><h1>EPI Cloud</h1>` +
      `<p>Sealed, witness-first evidence for AI agent runs. Vendors witness every run;` +
      ` reviewers check files in their own browser against signed checkpoints.</p>` +
      account +
      `<hr><p><a href="https://epilabs.org">epilabs.org</a> · ` +
      `<a href="https://epilabs.org/verify/">verify a file</a> · ` +
      `<a href="https://github.com/mohdibrahimaiml/epi-recorder">GitHub</a> · ` +
      `<a href="/.well-known/epi-witness-key.json">witness key</a></p></body></html>`,
  );
});

app.notFound((c) => c.json({ error: { code: "not_found", message: "Unknown route." } }, 404));

export { app };

async function scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
  ctx.waitUntil(
    (async () => {
      const checkpoints = await runCheckpointCron(env);
      const purge = await purgeExpiredArtifacts(env);
      // The single allowed print call in src (see test/log-hygiene):
      // counts only, never request data.
      console.log(`scheduled ok: ${checkpoints.checkpoints} checkpoints, ${purge.deleted} purged`);
    })().catch((err) => console.error("scheduled failed:", err)),
  );
}

export default { fetch: app.fetch, scheduled };
