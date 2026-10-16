import { Hono } from "hono";
import type { Env } from "./env.ts";
import { originAllowed, userFromRequest } from "./lib/auth.ts";
import { esc, page } from "./ui.ts";
import auth from "./routes/auth.ts";
import orgs from "./routes/orgs.ts";
import invites from "./routes/invites.ts";
import keys from "./routes/keys.ts";
import admin from "./routes/admin.ts";
import inboxes from "./routes/inboxes.ts";
import shares from "./routes/shares.ts";
import artifacts from "./routes/artifacts.ts";
import storage from "./routes/storage.ts";
import orgkeys, { publicKeys } from "./routes/orgkeys.ts";
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
app.route("/v1", orgkeys);
app.route("/", publicKeys);
app.route("/admin", admin);
app.route("/w", witness);
app.get("/.well-known/epi-witness-key.json", (c) => c.json(witnessKeys(c.env)));

// Front door (normal users never touch raw /auth URLs). Anonymous view is
// static HTML, no JS, no events, no signal: scanners and link previews
// create nothing. Signed-in view is the setup page in the epilabs.org visual
// language (inline only, no tracking): create workspace, API key (shown
// once), inbox, trust link, plus the exact `epi cloud login` command
// pre-filled with the org id. Trust links point at https://epilabs.org,
// which hosts the trust page — never at the cloud origin.
// Trust page origin (hosts /t/:id). The cloud API returns relative trust
// URLs; only this human dashboard renders the absolute site link.
const TRUST_ORIGIN = "https://epilabs.org";

app.get("/", async (c) => {
  let email: string | null = null;
  try {
    email = (await userFromRequest(c.env.DB, c.req.raw))?.email ?? null;
  } catch {
    email = null;
  }
  if (!email) {
    return c.html(
      page(
        "EPI Cloud — sealed evidence for AI runs",
        `<span class="tag">Sealed evidence for AI runs</span>` +
          `<h1>EPI Cloud</h1>` +
          `<p class="lede">Sealed, witness-first evidence for AI agent runs. Vendors witness every run;` +
          ` reviewers check files in their own browser against signed checkpoints.</p>` +
          `<p><a class="btn btn-pri" href="/auth/github">Sign in with GitHub</a></p>` +
          (c.env.GOOGLE_CLIENT_ID ? `<p><a class="btn btn-sec" href="/auth/google">Sign in with Google</a></p>` : ``) +
          `<p class="mut small">One account signs every recorder, inbox, and trust page.</p>`,
      ),
    );
  }
  const account =
    `<p>Signed in as <strong>${esc(email)}</strong>.</p>` +
    `<form method="post" action="/auth/logout"><button type="submit" class="btn btn-sec">Sign out</button></form>` +
    `<span class="tag">Setup (2 minutes)</span><h2>Setup</h2>` +
    `<div class="card"><strong>1. Workspace</strong><br>` +
    `<label for="org-name">Name</label><input id="org-name" placeholder="Acme Inc" autocomplete="organization">` +
    `<label for="org-slug">URL slug</label><input id="org-slug" placeholder="acme">` +
    `<p><button id="org-go" type="button" class="btn btn-pri">Create workspace</button></p>` +
    `<span id="org-msg" class="out small" role="status"></span></div>` +
    `<div class="card"><strong>2. Recorder key</strong><br>` +
    `<label for="org-pick">Workspace</label><select id="org-pick"></select>` +
    `<p><button id="key-go" type="button" class="btn btn-pri">Create API key</button> ` +
    `<button id="key-copy" type="button" class="btn btn-sec" style="display:none">Copy</button></p>` +
    `<span id="key-out" class="out small" role="status"></span><br><code id="login-cmd" class="out"></code></div>` +
    `<div class="card"><strong>3. Witness inbox</strong><br>` +
    `<label for="inbox-label">Customer / engagement</label><input id="inbox-label" placeholder="customer / engagement">` +
    `<p><button id="inbox-go" type="button" class="btn btn-pri">Create inbox</button></p>` +
    `<span id="inbox-out" class="out small" role="status"></span></div>` +
    `<div class="card"><strong>4. Trust link</strong><br>` +
    `<label for="share-label">Reviewer / deal</label><input id="share-label" placeholder="reviewer / deal">` +
    `<p><button id="share-go" type="button" class="btn btn-pri">Create trust link</button></p>` +
    `<span id="share-out" class="out small" role="status"></span></div>` +
    `<div class="card"><strong>5. Connect this computer</strong>` +
    `<p class="small">Run <code>epi cloud login</code> in your terminal, type the short code it shows at ` +
    `<a href="/auth/device">Authorize this computer</a>, and the CLI picks up a push-only key by itself.</p></div>`;
  const script = [
    `var TRUST_ORIGIN=${JSON.stringify(TRUST_ORIGIN)};`,
    `var pick=document.getElementById("org-pick");`,
    `var cmd=document.getElementById("login-cmd");`,
    `function refreshOrgs(){`,
    `  fetch("/v1/orgs",{credentials:"same-origin"})`,
    `    .then(function(r){return r.json();})`,
    `    .then(function(j){`,
    `      pick.innerHTML="";`,
    `      (j.orgs||[]).forEach(function(o){`,
    `        var e=document.createElement("option");`,
    `        e.value=o.id;`,
    `        e.textContent=o.name+" ("+o.id+")";`,
    `        pick.appendChild(e);`,
    `      });`,
    `      if(pick.value){cmd.textContent="epi cloud login --url "+location.origin+" --org "+pick.value+" --api-key <paste-key>";}`,
    `    });`,
    `}`,
    `refreshOrgs();`,
    `document.getElementById("org-go").onclick=function(){`,
    `  var n=document.getElementById("org-name").value;`,
    `  var s=document.getElementById("org-slug").value;`,
    `  fetch("/v1/orgs",{method:"POST",credentials:"same-origin",`,
    `    headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n,slug:s})})`,
    `    .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})`,
    `    .then(function(x){`,
    `      document.getElementById("org-msg").textContent=x.ok?("Created "+x.j.id):("Failed: "+((x.j.error&&x.j.error.message)||"unknown"));`,
    `      refreshOrgs();`,
    `    });`,
    `};`,
    `var lastKey="";`,
    `document.getElementById("key-go").onclick=function(){`,
    `  if(!pick.value){return;}`,
    `  fetch("/v1/orgs/"+pick.value+"/api-keys",{method:"POST",credentials:"same-origin",`,
    `    headers:{"Content-Type":"application/json"},body:JSON.stringify({scopes:["push"]})})`,
    `    .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})`,
    `    .then(function(x){`,
    `      if(x.ok){`,
    `        lastKey=x.j.key;`,
    `        document.getElementById("key-out").textContent="Key (shown once): "+lastKey;`,
    `        document.getElementById("key-copy").style.display="inline";`,
    `        cmd.textContent="epi cloud login --url "+location.origin+" --org "+pick.value+" --api-key "+lastKey;`,
    `      }else{`,
    `        document.getElementById("key-out").textContent="Failed: "+((x.j.error&&x.j.error.message)||"unknown");`,
    `      }`,
    `    });`,
    `};`,
    `document.getElementById("key-copy").onclick=function(){`,
    `  if(navigator.clipboard&&lastKey){navigator.clipboard.writeText(lastKey);}`,
    `};`,
    `document.getElementById("inbox-go").onclick=function(){`,
    `  if(!pick.value){return;}`,
    `  var l=document.getElementById("inbox-label").value||"customer";`,
    `  fetch("/v1/orgs/"+pick.value+"/inboxes",{method:"POST",credentials:"same-origin",`,
    `    headers:{"Content-Type":"application/json"},body:JSON.stringify({customer_label:l})})`,
    `    .then(function(r){return r.json();})`,
    `    .then(function(j){`,
    `      document.getElementById("inbox-out").textContent=j.url?("Inbox "+j.url+" \\u2014 secret shown once: "+j.secret):("Failed: "+((j.error&&j.error.message)||"unknown"));`,
    `    });`,
    `};`,
    `document.getElementById("share-go").onclick=function(){`,
    `  if(!pick.value){return;}`,
    `  var l=document.getElementById("share-label").value||"review";`,
    `  fetch("/v1/orgs/"+pick.value+"/share-links",{method:"POST",credentials:"same-origin",`,
    `    headers:{"Content-Type":"application/json"},body:JSON.stringify({label:l})})`,
    `    .then(function(r){return r.json();})`,
    `    .then(function(j){`,
    `      document.getElementById("share-out").textContent=j.url?(TRUST_ORIGIN+"/t/"+j.id+"#k="+j.token+" (token shown once)"):("Failed: "+((j.error&&j.error.message)||"unknown"));`,
    `    });`,
    `};`,
  ].join("\n");
  return c.html(
    page("EPI Cloud — setup", `<span class="tag">Signed in</span>` + account, { script }),
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
