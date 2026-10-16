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

// Front door (normal users never touch raw /auth URLs). Anonymous view is
// static HTML, no JS, no events, no signal: scanners and link previews
// create nothing. Signed-in view is a minimal setup page (plain HTML, no
// tracking): create workspace, API key (shown once), inbox, trust link,
// plus the exact `epi cloud login` command pre-filled with the org id.
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
       <h2>Setup (2 minutes)</h2>
       <ol>
         <li><strong>Workspace:</strong> <input id="org-name" placeholder="Acme Inc" style="font:inherit;padding:.3rem"> <input id="org-slug" placeholder="acme" style="font:inherit;padding:.3rem"> <button id="org-go" type="button">Create workspace</button> <span id="org-msg"></span></li>
         <li><strong>Recorder key:</strong> <select id="org-pick" style="font:inherit;padding:.3rem"></select> <button id="key-go" type="button">Create API key</button><br><span id="key-out"></span> <button id="key-copy" type="button" style="display:none">Copy</button><br><code id="login-cmd"></code></li>
         <li><strong>Witness inbox:</strong> <input id="inbox-label" placeholder="customer / engagement" style="font:inherit;padding:.3rem"> <button id="inbox-go" type="button">Create inbox</button> <span id="inbox-out"></span></li>
         <li><strong>Trust link:</strong> <input id="share-label" placeholder="reviewer / deal" style="font:inherit;padding:.3rem"> <button id="share-go" type="button">Create trust link</button> <span id="share-out"></span></li>
       </ol>
       <p>Or connect automatically: run <code>epi cloud login</code> in your terminal, then click “Authorize this computer” here.</p>
       <script>
       (function(){
         var pick=document.getElementById("org-pick"),cmd=document.getElementById("login-cmd");
         function refreshOrgs(){fetch("/v1/orgs",{credentials:"same-origin"}).then(function(r){return r.json()}).then(function(j){
           pick.innerHTML="";(j.orgs||[]).forEach(function(o){var e=document.createElement("option");e.value=o.id;e.textContent=o.name+" ("+o.id+")";pick.appendChild(e)});
           if(pick.value)cmd.textContent="epi cloud login --url "+location.origin+" --org "+pick.value+" --api-key <paste-key>";});}
         refreshOrgs();
         document.getElementById("org-go").onclick=function(){var n=document.getElementById("org-name").value,s=document.getElementById("org-slug").value;
           fetch("/v1/orgs",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n,slug:s})})
           .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}})}).then(function(x){
             document.getElementById("org-msg").textContent=x.ok?("Created "+x.j.id):("Failed: "+((x.j.error&&x.j.error.message)||"unknown"));refreshOrgs();});};
         var lastKey="";
         document.getElementById("key-go").onclick=function(){if(!pick.value)return;
           fetch("/v1/orgs/"+pick.value+"/api-keys",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({scopes:["push"]})})
           .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}})}).then(function(x){
             if(x.ok){lastKey=x.j.key;document.getElementById("key-out").textContent="Key (shown once): "+lastKey;
               document.getElementById("key-copy").style.display="inline";
               cmd.textContent="epi cloud login --url "+location.origin+" --org "+pick.value+" --api-key "+lastKey;}
             else document.getElementById("key-out").textContent="Failed: "+((x.j.error&&x.j.error.message)||"unknown")});};
         document.getElementById("key-copy").onclick=function(){if(navigator.clipboard&&lastKey)navigator.clipboard.writeText(lastKey);};
         document.getElementById("inbox-go").onclick=function(){if(!pick.value)return;var l=document.getElementById("inbox-label").value||"customer";
           fetch("/v1/orgs/"+pick.value+"/inboxes",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({customer_label:l})})
           .then(function(r){return r.json()}).then(function(j){document.getElementById("inbox-out").textContent=j.url?("Inbox "+j.url+" — secret shown once: "+j.secret):("Failed: "+((j.error&&j.error.message)||"unknown"))});};
         document.getElementById("share-go").onclick=function(){if(!pick.value)return;var l=document.getElementById("share-label").value||"review";
           fetch("/v1/orgs/"+pick.value+"/share-links",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({label:l})})
           .then(function(r){return r.json()}).then(function(j){document.getElementById("share-out").textContent=j.url?("Trust link "+location.origin+"/t/"+j.id+"#k="+j.token+" (token shown once)"):("Failed: "+((j.error&&j.error.message)||"unknown"))});};
       })();
       </script>`
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
