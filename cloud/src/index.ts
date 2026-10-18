import { Hono } from "hono";
import type { Env } from "./env.ts";
import { originAllowed, userFromRequest } from "./lib/auth.ts";
import { esc, page } from "./ui.ts";
import auth, { MIN_CLI_VERSION } from "./routes/auth.ts";
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
  // One-line cause for `wrangler tail` / Cloudflare Logs. Message only:
  // never request data, tokens, or cookies (none of those live on `err`).
  console.error(`request failed: ${err instanceof Error ? err.message : String(err)}`);
  return c.json({ error: { code: "internal", message: "Unexpected error." } }, 500);
});

app.get("/health", (c) => c.json({ ok: true, service: "epi-cloud", m: 1 }));
// Public version gate: lets old CLIs warn instead of failing mysteriously.
app.get("/v1/version", (c) => c.json({ service: "epi-cloud", min_cli_version: MIN_CLI_VERSION }));
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
    `<p><label for="org-pick">Workspace</label><select id="org-pick"></select></p>` +
    `<div id="reveal" style="display:none"></div>` +
    `<div id="loading"><p class="mut">Loading your workspaces…</p></div>` +
    `<div id="guide" style="display:none">` +
    `<span class="tag">Guided start</span><h2>Get set up in 5 steps</h2>` +
    `<p class="lede">Each step unlocks the next. Nothing here is final — every name can change later.</p>` +
    `<div id="steps"></div></div>` +
    `<div id="dash" style="display:none">` +
    `<span class="tag">Dashboard</span><h2>Your evidence</h2>` +
    `<p class="ok">Setup complete — every step below is live. Add customers and trust links any time.</p>` +
    `<div class="tabs" role="tablist">` +
    `<button type="button" class="tab active" data-tab="runs" role="tab">Runs</button>` +
    `<button type="button" class="tab" data-tab="customers" role="tab">Customers</button>` +
    `<button type="button" class="tab" data-tab="links" role="tab">Trust links</button>` +
    `<button type="button" class="tab" data-tab="keys" role="tab">Computers &amp; keys</button>` +
    `</div>` +
    `<div id="tab-runs" role="tabpanel"></div>` +
    `<div id="tab-customers" role="tabpanel" style="display:none"></div>` +
    `<div id="tab-links" role="tabpanel" style="display:none"></div>` +
    `<div id="tab-keys" role="tabpanel" style="display:none"></div>` +
    `</div>`;
  const script = [
    `var TRUST_ORIGIN=${JSON.stringify(TRUST_ORIGIN)};`,
    `var S={orgs:[],org:null,agents:[],keys:null,runs:[],inboxes:[],links:null,linksForbidden:false,reveal:null};`,
    `var timers=[];`,
    `function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(ch){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];});}`,
    `function localTime(iso){try{var d=new Date(iso);if(isNaN(d.getTime())){return iso;}return d.toLocaleString();}catch(e){return iso;}}`,
    `function slugify(n){return String(n||"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"").slice(0,50);}`,
    `function api(path,opts){opts=opts||{};return fetch(path,{method:opts.method||"GET",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:opts.body?JSON.stringify(opts.body):undefined}).then(function(r){return r.json().catch(function(){return {};}).then(function(j){return {ok:r.ok,status:r.status,json:j};});}).catch(function(){return {ok:false,status:0,json:{}};});}`,
    `function friendlyErr(action,status,j){var m=j&&j.error&&j.error.message;if(status===0){return "Couldn't reach the cloud — check your connection, then retry.";}if(status===401){return "Your sign-in expired — sign in again, then retry.";}if(status===403){return "Only workspace owners can do this — ask an owner.";}if(status===409){return "That name is already taken — try another.";}if(status===429){return "Too many tries — wait a minute, then retry.";}if(m){return m;}return "Something went wrong "+action+" — try again.";}`,
    `function copyText(t,msgEl){function done(m){if(msgEl){msgEl.textContent=m;}}if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(function(){done("Copied.");},function(){done("Copy failed — select the text manually.");});return;}var ta=document.createElement("textarea");ta.value=t;document.body.appendChild(ta);ta.select();try{document.execCommand("copy");done("Copied.");}catch(e){done("Copy failed — select the text manually.");}document.body.removeChild(ta);}`,
    `function stopTimers(){timers.forEach(function(t){clearInterval(t);});timers=[];}`,
    `function sealBadge(check){if(check==="valid"){return '<span class="pill ok">Seal \\u2713</span>';}if(check==="invalid"){return '<span class="pill bad">Seal \\u2717</span>';}return '<span class="pill">Unsigned</span>';}`,
    `function witBadge(st){if(st==="witnessed"){return '<span class="pill ok">Witnessed \\u2713</span>';}if(st==="no_inbox"){return '<span class="pill">No inbox</span>';}if(st==="not_in_witness"){return '<span class="pill">Not witnessed</span>';}if(st==="different_version"){return '<span class="pill bad">Different version</span>';}return '<span class="pill">'+esc(st)+'</span>';}`,
    `function agentName(id){var a=(S.agents||[]).filter(function(x){return x.id===id;})[0];return a?a.name:"";}`,
    `function inboxLabel(id){var b=(S.inboxes||[]).filter(function(x){return x.id===id;})[0];return b?b.customer_label:"";}`,
    `function runsForCustomer(label){return (S.runs||[]).filter(function(r){return r.agent_id&&agentName(r.agent_id)===label;});}`,
    `function scopeNames(scope){var an=scope.agents==="all"?["All recorders"]:(scope.agents||[]).map(function(id){return agentName(id)||id;});var bn=scope.inboxes==="all"?["All customers"]:(scope.inboxes||[]).map(function(id){return inboxLabel(id)||id;});return {agents:an,inboxes:bn};}`,
    `function boot(){api("/v1/orgs").then(function(x){S.orgs=(x.ok&&x.json.orgs)||[];var pick=document.getElementById("org-pick");pick.innerHTML="";if(!S.orgs.length){var o=document.createElement("option");o.value="";o.textContent="No workspace yet — start below";pick.appendChild(o);S.org=null;render();return;}S.orgs.forEach(function(o){var el=document.createElement("option");el.value=o.id;el.textContent=o.name;pick.appendChild(el);});S.org=S.orgs[0].id;pick.value=S.org;loadAll();});}`,
    `document.getElementById("org-pick").onchange=function(){S.org=this.value||null;if(S.org){loadAll();}else{render();}};`,
    `function loadAll(){stopTimers();var id=S.org;Promise.all([api("/v1/orgs/"+id+"/agents"),api("/v1/orgs/"+id+"/api-keys"),api("/v1/orgs/"+id+"/artifacts"),api("/v1/orgs/"+id+"/inboxes"),api("/v1/orgs/"+id+"/share-links")]).then(function(rs){S.agents=(rs[0].ok&&rs[0].json.agents)||[];S.keys=rs[1].ok?(rs[1].json.keys||[]):(rs[1].status===403?"forbidden":null);S.runs=(rs[2].ok&&rs[2].json.artifacts)||[];S.inboxes=(rs[3].ok&&rs[3].json.inboxes)||[];if(rs[4].ok){S.links=rs[4].json.links||[];S.linksForbidden=false;}else{S.links=null;S.linksForbidden=rs[4].status===403;}render();});}`,
    `function milestones(){return {org:!!S.org,key:!!(S.keys&&S.keys.length),run:S.runs.length>0,customer:S.inboxes.length>0,link:!!(S.links&&S.links.length)};}`,
    `function currentStep(m){var s=currentStepRaw(m);if(S.reveal){if(S.reveal.kind==="inbox"&&s>4){return 4;}if(S.reveal.kind==="link"&&s>5){return 5;}}return s;}`,
    `function currentStepRaw(m){if(!m.org){return 1;}if(!m.key){return 2;}if(!m.run){return 3;}if(!m.customer){return 4;}if(!m.link){return 5;}return 6;}`,
    `function render(){stopTimers();var m=milestones();var step=currentStep(m);document.getElementById("loading").style.display="none";if(step>5){renderDash();return;}document.getElementById("dash").style.display="none";document.getElementById("guide").style.display="";renderGuide(m,step);}`,
    `function stepShell(n,title,state,inner){var mark=state==="done"?'<span class="mark done">\\u2713 done</span>':(state==="current"?'<span class="mark">step '+n+' of 5</span>':'<span class="mark">locked</span>');return '<div class="step '+state+'"><div class="stephead"><span class="stepnum">'+n+'</span><strong>'+title+'</strong>'+mark+'</div><div class="stepbody">'+inner+'</div></div>';}`,
    `function renderGuide(m,step){var h="";`,
    `h+=stepShell(1,"Name your company",step>1?"done":(step===1?"current":"locked"),stepHtml1(step===1,m));`,
    `h+=stepShell(2,"Connect your computer",m.key?"done":(step===2?"current":"locked"),stepHtml2(step===2,m));`,
    `h+=stepShell(3,"Record your first run",m.run?"done":(step===3?"current":"locked"),stepHtml3(step===3,m));`,
    `h+=stepShell(4,"Add a customer",m.customer?"done":(step===4?"current":"locked"),stepHtml4(step===4,m));`,
    `h+=stepShell(5,"Share with that customer's reviewer",m.link?"done":(step===5?"current":"locked"),stepHtml5(step===5,m));`,
    `document.getElementById("steps").innerHTML=h;wireGuide(step,m);`,
    `if(step===2&&!m.key){timers.push(setInterval(function(){api("/v1/orgs/"+S.org+"/api-keys").then(function(x){if(x.ok&&(x.json.keys||[]).length){loadAll();}});},5000));}`,
    `if(step===3&&!m.run){timers.push(setInterval(function(){api("/v1/orgs/"+S.org+"/artifacts").then(function(x){if(x.ok&&(x.json.artifacts||[]).length){loadAll();}});},5000));}`,
    `}`,
    `function stepHtml1(active,m){if(!active){return m.org?'<p class="small">Workspace: <strong>'+esc(orgName())+'</strong></p>':'<p class="small">Create a workspace first.</p>';}return '<p>What company is this evidence for? One box — the short web name fills itself in.</p><label for="org-name">Company name</label><input id="org-name" placeholder="Acme AI" autocomplete="organization"><details class="adv"><summary>Advanced: edit the short name</summary><label for="org-slug">Short name (letters, numbers, dashes)</label><input id="org-slug" placeholder="acme-ai"></details><p><button id="org-go" type="button" class="btn btn-pri">Create workspace</button></p><p id="org-msg" class="small" role="status"></p>';}`,
    `function orgName(){var o=(S.orgs||[]).filter(function(x){return x.id===S.org;})[0];return o?o.name:"";}`,
    `function stepHtml2(active,m){if(!active){return '<p class="small">'+(S.keys?S.keys.length:0)+' computer(s) connected.</p>';}var origin=location.origin;return '<p>On your computer, run these two commands (<button type="button" class="btn btn-sec" id="s2-c1b">Copy</button>):</p><pre class="cmd" id="s2-c1">pip install -U epi-recorder<br>epi cloud login --url '+esc(origin)+'</pre><p class="small">Needs epi-recorder 4.6.2 or newer — check with <code>epi --version</code>. Then type the short code it shows at <a href="/auth/device">Authorize this computer</a>. This page turns green by itself when your computer connects.</p><p id="s2-msg" class="small" role="status">Waiting for your computer…</p>';}`,
    `function stepHtml3(active,m){if(!active){return '<p class="small">'+S.runs.length+' run(s) recorded.</p>';}return '<p>Seal one real run, then push the run you chose to share (<button type="button" class="btn btn-sec" id="s3-cb">Copy</button>):</p><pre class="cmd" id="s3-c">epi record --out run.epi -- python app.py<br>epi cloud push run.epi --reason sample</pre><p class="small">Push only runs you mean to share — every run stays private until you push it. This page turns green when the first run arrives.</p><p id="s3-msg" class="small" role="status">Waiting for the first run…</p>';}`,
    `function stepHtml4(active,m){if(!active){return '<p class="small">'+S.inboxes.length+' customer(s).</p>';}return '<p>Who is this evidence for? A customer gets their own witness inbox — runs reported there never mix with another customer\\u2019s.</p><label for="cust-name">Customer name (e.g. Acme Bank)</label><input id="cust-name" placeholder="Acme Bank"><p><button id="cust-go" type="button" class="btn btn-pri">Add customer</button></p><p id="cust-msg" class="small" role="status"></p><div id="cust-env"></div>';}`,
    `function stepHtml5(active,m){if(!active){return '<p class="small">'+((S.links||[]).length)+' trust link(s).</p>';}var opts=(S.inboxes||[]).filter(function(b){return !b.closed_at;}).map(function(b){return '<option value="'+esc(b.id)+'">'+esc(b.customer_label)+'</option>';}).join("");return '<p>The link shows <strong>only this customer\\u2019s</strong> runs — never the whole workspace.</p><label for="link-cust">Customer</label><select id="link-cust">'+opts+'</select><label for="link-label">Link name</label><input id="link-label" placeholder="Acme Bank review"><p><label><input type="checkbox" id="link-all" style="width:auto"> Share <strong>all</strong> customers on this link</label></p><div id="link-warn" class="warn small" style="display:none">Warning: anyone with this link sees every customer\\u2019s runs. Only use this for internal review.</div><p><button id="link-go" type="button" class="btn btn-pri">Create trust link</button></p><p id="link-msg" class="small" role="status"></p><div id="link-out"></div>';}`,
  ].join("\n");
  const script2 = [
    `function byId(id){return document.getElementById(id);}`,
    `function wireGuide(step,m){`,
    `var nm=byId("org-name");`,
    `if(nm){var sl=byId("org-slug");var touched=false;sl.oninput=function(){touched=true;};nm.oninput=function(){if(!touched){sl.value=slugify(nm.value);}};byId("org-go").onclick=function(){createOrg(nm.value,sl.value||slugify(nm.value),byId("org-msg"));};}`,
    `var c1=byId("s2-c1b");if(c1){c1.onclick=function(){copyText(byId("s2-c1").textContent,byId("s2-msg"));};}`,
    `var c3=byId("s3-cb");if(c3){c3.onclick=function(){copyText(byId("s3-c").textContent,byId("s3-msg"));};}`,
    `var cg=byId("cust-go");if(cg){cg.onclick=function(){var l=byId("cust-name").value.trim();if(!l){byId("cust-msg").textContent="Give the customer a name first.";return;}byId("cust-msg").textContent="Creating…";createCustomer(l,byId("cust-msg"),byId("cust-env"),function(){loadAll();});};}`,
        `var la=byId("link-all");if(la){la.onchange=function(){byId("link-warn").style.display=la.checked?"":"none";};}`,
    `var lg=byId("link-go");if(lg){lg.onclick=function(){createLink(byId("link-cust").value,byId("link-label").value.trim(),byId("link-all").checked,byId("link-msg"),byId("link-out"),function(){loadAll();});};}`,
    `}`,
    `function createOrg(name,slug,msgEl){api("/v1/orgs",{method:"POST",body:{name:name,slug:slug}}).then(function(x){if(!x.ok){msgEl.textContent=friendlyErr("creating the workspace",x.status,x.json);return;}msgEl.textContent="Workspace created.";S.org=x.json.id;S.orgs.push({id:x.json.id,name:x.json.name});var pick=byId("org-pick");var el=document.createElement("option");el.value=x.json.id;el.textContent=x.json.name;pick.appendChild(el);pick.value=x.json.id;loadAll();});}`,
    `function setReveal(obj){S.reveal=obj||null;renderReveal();}`,
    `function renderReveal(){var box=document.getElementById("reveal");if(!box){return;}var r=S.reveal;if(!r){box.style.display="none";box.innerHTML="";return;}box.style.display="";var h="";if(r.kind==="inbox"){h+='<div class="warn small">Save this now \u2014 the secret is shown once, then never again.</div><p><label>Paste into the recorder\u2019s environment</label></p><div class="copyrow"><code>EPI_WITNESS_URL='+esc(r.url)+'</code><button type="button" class="btn btn-sec" data-c="url">Copy</button></div><div class="copyrow"><code>EPI_WITNESS_SECRET='+esc(r.secret)+'</code><button type="button" class="btn btn-sec" data-c="secret">Copy</button></div>'+ '<p><label>Push this run tagged to the customer</label></p><div class="copyrow"><code>epi cloud push run.epi --reason sample --agent "'+esc(r.label)+'"</code><button type="button" class="btn btn-sec" data-c="push">Copy</button></div>';}else if(r.kind==="rotate"){h+='<div class="warn small">Rotated \u2014 old secret no longer works. Save the new secret now; it is shown once.</div><p><label>Paste into the recorder\u2019s environment</label></p><div class="copyrow"><code>EPI_WITNESS_URL='+esc(r.url)+'</code><button type="button" class="btn btn-sec" data-c="url">Copy</button></div><div class="copyrow"><code>EPI_WITNESS_SECRET='+esc(r.secret)+'</code><button type="button" class="btn btn-sec" data-c="secret">Copy</button></div>';}else if(r.kind==="link"){h+='<div class="warn small">Link created \u2014 the token is shown once, then never again.</div><div class="copyrow"><code>'+esc(r.url)+'</code><button type="button" class="btn btn-sec" data-c="url">Copy</button></div><p><a class="btn btn-sec" href="'+esc(r.url)+'" target="_blank" rel="noopener">Preview as reviewer</a></p>';}else if(r.kind==="key"){h+='<div class="warn small">Key created \u2014 shown once, copy it now.</div><div class="copyrow"><code>'+esc(r.secret)+'</code><button type="button" class="btn btn-sec" data-c="secret">Copy</button></div>';}h+='<p id="reveal-msg" class="small" role="status"></p><p><button id="reveal-ack" type="button" class="btn btn-pri">I\u2019ve saved it</button></p>';box.innerHTML=h;var cs=box.querySelectorAll("button[data-c]");for(var k=0;k<cs.length;k++){(function(b){b.onclick=function(){var what=b.getAttribute("data-c");var txt=what==="push"?(("epi cloud push run.epi --reason sample --agent \\""+r.label+"\\"")):what==="url"?("link"===r.kind?r.url:("key"===r.kind?r.secret:("EPI_WITNESS_URL="+r.url))):("key"===r.kind?r.secret:("EPI_WITNESS_SECRET="+r.secret));copyText(txt,document.getElementById("reveal-msg"));};})(cs[k]);}document.getElementById("reveal-ack").onclick=function(){ackReveal();};}`,
    `function ackReveal(){S.reveal=null;renderReveal();loadAll();}`,
    `function createCustomer(label,msgEl,outEl,done){api("/v1/orgs/"+S.org+"/inboxes",{method:"POST",body:{customer_label:label}}).then(function(x){if(!x.ok){msgEl.textContent=friendlyErr("adding the customer",x.status,x.json);return null;}return x.json;}).then(function(inbox){if(!inbox){return;}ensureAgent(label).then(function(agent){if(!agent){msgEl.textContent="Inbox created, but the recorder name is taken by something else \u2014 ask an owner.";if(done){done();}return;}msgEl.textContent="Customer added. Secret shown above \u2014 copy it, then click I\u2019ve saved it.";setReveal({kind:"inbox",id:inbox.id,url:inbox.url,secret:inbox.secret,label:label});if(done){done();}});});}`,
    `function rotateSecret(inboxId,label,msgEl){if(!confirm("Rotate witness secret for "+label+"? The old secret stops working immediately. Update \`EPI_WITNESS_SECRET\` on every machine that reports for this customer. Runs already witnessed stay valid.")){return;}msgEl.textContent="Rotating\u2026";api("/v1/orgs/"+S.org+"/inboxes/"+inboxId+"/rotate",{method:"POST"}).then(function(x){if(!x.ok){msgEl.textContent=friendlyErr("rotating the secret",x.status,x.json);return;}msgEl.textContent="Rotated \u2014 old secret no longer works. New secret shown above.";setReveal({kind:"rotate",id:x.json.id,url:x.json.url,secret:x.json.secret,label:label});loadAll();});}`,


    `function ensureAgent(label){return api("/v1/orgs/"+S.org+"/agents",{method:"POST",body:{name:label}}).then(function(x){if(x.ok){return x.json;}if(x.status===409){return api("/v1/orgs/"+S.org+"/agents").then(function(y){if(!y.ok){return null;}var f=(y.json.agents||[]).filter(function(a){return a.name===label;})[0];return f||null;});}return null;});}`,
    `function createLink(inboxId,label,all,msgEl,outEl,done){var agents=(S.agents||[]);var agent=null;if(!all){var inb=(S.inboxes||[]).filter(function(b){return b.id===inboxId;})[0];var want=inb?inb.customer_label:"";agent=agents.filter(function(a){return a.name===want;})[0];if(!agent){msgEl.textContent="No recorder named \\u201C"+want+"\\u201D yet — add the customer again, or tick all-customers.";return;}}var scope=all?{agents:"all",inboxes:"all"}:{agents:[agent.id],inboxes:[inboxId]};var name=label||((all?"Workspace":inboxLabel(inboxId))+" review");msgEl.textContent="Creating…";api("/v1/orgs/"+S.org+"/share-links",{method:"POST",body:{label:name,scope:scope}}).then(function(x){if(!x.ok){msgEl.textContent=friendlyErr("creating the link",x.status,x.json);return;}var url=TRUST_ORIGIN+"/t/"+x.json.id+"#k="+x.json.token;msgEl.textContent="Link created. Token shown above \u2014 copy it, then click I\u2019ve saved it.";setReveal({kind:"link",url:url,label:name});done();});}`,
    `function renderDash(){document.getElementById("guide").style.display="none";var d=document.getElementById("dash");d.style.display="";renderRuns();renderCustomers();renderLinks();renderKeys();}`,
    `document.querySelectorAll("button.tab").forEach(function(b){b.onclick=function(){document.querySelectorAll("button.tab").forEach(function(x){x.classList.remove("active");});b.classList.add("active");["runs","customers","links","keys"].forEach(function(t){document.getElementById("tab-"+t).style.display=(t===b.getAttribute("data-tab"))?"":"none";});};});`,
    `function emptyRow(cols,msg){return '<tr><td colspan="'+cols+'">'+msg+'</td></tr>';}`,
    `function assignRun(id,label){api("/v1/orgs/"+S.org+"/artifacts/"+id+"/agent",{method:"PATCH",body:{agent:label}}).then(function(x){if(!x.ok){alert(friendlyErr("assigning the run",x.status,x.json));return;}loadAll();});}`,
    `function renderRuns(){var el=document.getElementById("tab-runs");var rows=(S.runs||[]).map(function(r){var cust=(r.agent_id&&agentName(r.agent_id))||"Unassigned";var assign="";if(!r.agent_id){var opts=(S.inboxes||[]).filter(function(b){return !b.closed_at;}).map(function(b){return '<option value="'+esc(b.customer_label)+'">'+esc(b.customer_label)+'</option>';}).join("");if(opts){assign='<div class="small" style="margin-top:.4rem"><select data-assign="'+esc(r.id)+'">'+opts+'</select> <button type="button" class="btn btn-sec" data-assignbtn="'+esc(r.id)+'">Assign</button></div>';}}return '<tr><td>'+esc(r.goal||r.workflow_id||r.id)+'</td><td>'+sealBadge(r.signature_check)+'</td><td>'+witBadge(r.witness_status)+'</td><td>'+esc(cust)+assign+'</td><td class="small">'+esc(localTime(r.uploaded_at||r.sealed_at||""))+'</td></tr>';}).join("");el.innerHTML='<h3>Runs</h3><p class="small mut">Every selected run pushed to this workspace. Runs land under \\u201CUnassigned\\u201D until tagged to a customer: push new runs with <code>--agent "NAME"</code>, or assign one below.</p><div class="twrap"><table class="tbl"><thead><tr><th>Run</th><th>Seal</th><th>Witness</th><th>Customer</th><th>Pushed</th></tr></thead><tbody>'+(rows||emptyRow(5,"No runs yet — record your first run (guided step 3)."))+'</tbody></table></div>';el.querySelectorAll("button[data-assignbtn]").forEach(function(btn){btn.onclick=function(){var id=btn.getAttribute("data-assignbtn");var sel=el.querySelector('select[data-assign="'+id+'"]');var label=sel?sel.value:"";if(!label){return;}assignRun(id,label);};});}`,
    `function renderCustomers(){var el=document.getElementById("tab-customers");var rows=(S.inboxes||[]).map(function(b){var n=runsForCustomer(b.customer_label).length;var st=b.closed_at?'<span class="pill">Closed</span>':'<span class="pill ok">Open</span>';var btn=b.closed_at?"":' <button type="button" class="btn btn-sec" data-close="'+esc(b.id)+'">Close</button>';var rot=b.closed_at?"":' <button type="button" class="btn btn-sec" data-rotate="'+esc(b.id)+'" data-label="'+esc(b.customer_label)+'">Rotate secret</button>';return '<tr><td>'+esc(b.customer_label)+'</td><td class="small">'+esc(b.id)+'</td><td>'+n+'</td><td class="small">'+esc(localTime(b.created_at))+'</td><td>'+st+btn+rot+'</td></tr>';}).join("");el.innerHTML='<h3>Customers</h3><p class="small mut">One witness inbox per customer. Closing stops new reports to that inbox.</p><div class="twrap"><table class="tbl"><thead><tr><th>Customer</th><th>Inbox</th><th>Runs</th><th>Added</th><th>Status</th></tr></thead><tbody>'+(rows||emptyRow(5,"No customers yet — add one below."))+'</tbody></table></div><div class="card" id="tab-rotate-card"><strong>Rotate a witness secret</strong><p class="small mut">If a secret leaked, rotate it. The old secret stops working immediately — already witnessed runs stay valid.</p><p id="tab-rotate-msg" class="small" role="status"></p><div id="tab-rotate-out"></div></div><div class="card"><strong>Add a customer</strong><br><label for="tab-cust-name">Customer name</label><input id="tab-cust-name" placeholder="Acme Bank"><p><button id="tab-cust-go" type="button" class="btn btn-pri">Add customer</button></p><p id="tab-cust-msg" class="small" role="status"></p><div id="tab-cust-env"></div></div>';el.querySelectorAll("button[data-close]").forEach(function(btn){btn.onclick=function(){if(!confirm("Close this inbox? Recorders can no longer report to it.")){return;}api("/v1/orgs/"+S.org+"/inboxes/"+btn.getAttribute("data-close")+"/close",{method:"POST"}).then(function(x){if(!x.ok){alert(friendlyErr("closing the inbox",x.status,x.json));return;}loadAll();});};});el.querySelectorAll("button[data-rotate]").forEach(function(btn){btn.onclick=function(){rotateSecret(btn.getAttribute("data-rotate"),btn.getAttribute("data-label")||btn.getAttribute("data-rotate"),document.getElementById("tab-rotate-msg"));};});document.getElementById("tab-cust-go").onclick=function(){var l=document.getElementById("tab-cust-name").value.trim();if(!l){document.getElementById("tab-cust-msg").textContent="Give the customer a name first.";return;}createCustomer(l,document.getElementById("tab-cust-msg"),document.getElementById("tab-cust-env"),function(){loadAll();});};}`,
    `function renderLinks(){var el=document.getElementById("tab-links");function forNames(scope){var s=scopeNames(scope);return esc(s.inboxes.join(", "));}var rows=(S.links||[]).map(function(l){var scope={};try{scope=JSON.parse(l.scope);}catch(e){scope={agents:"all",inboxes:"all"};}var exp=localTime(l.expires_at);var st=l.revoked_at?'<span class="pill bad">Revoked</span>':'<span class="pill ok">Live</span>';var btn=l.revoked_at?"":' <button type="button" class="btn btn-sec" data-revoke="'+esc(l.id)+'">Revoke</button>';return '<tr data-link="'+esc(l.id)+'"><td>'+esc(l.label)+'</td><td>'+forNames(scope)+'</td><td class="small">'+esc(exp)+'</td><td class="small ev">Loading activity…</td><td>'+st+btn+'</td></tr>';}).join("");el.innerHTML='<h3>Trust links</h3><p class="small mut">Each link opens the reviewer trust page. Links are scoped to one customer unless you tick all-customers.</p><div class="twrap"><table class="tbl"><thead><tr><th>Link</th><th>For</th><th>Expires</th><th>Activity</th><th>Status</th></tr></thead><tbody>'+(rows||emptyRow(5,"No trust links yet — create one for a customer."))+'</tbody></table></div><div class="card"><strong>New trust link</strong><br><label for="tab-link-cust">Customer</label><select id="tab-link-cust">'+(S.inboxes||[]).filter(function(b){return !b.closed_at;}).map(function(b){return '<option value="'+esc(b.id)+'">'+esc(b.customer_label)+'</option>';}).join("")+'</select><label for="tab-link-label">Link name</label><input id="tab-link-label" placeholder="Acme Bank review"><p><label><input type="checkbox" id="tab-link-all" style="width:auto"> Share <strong>all</strong> customers on this link</label></p><div id="tab-link-warn" class="warn small" style="display:none">Warning: anyone with this link sees every customer\\u2019s runs. Only use this for internal review.</div><p><button id="tab-link-go" type="button" class="btn btn-pri">Create trust link</button></p><p id="tab-link-msg" class="small" role="status"></p><div id="tab-link-out"></div></div>';el.querySelectorAll("button[data-revoke]").forEach(function(btn){btn.onclick=function(){if(!confirm("Revoke this link? Reviewers immediately lose access.")){return;}api("/v1/orgs/"+S.org+"/share-links/"+btn.getAttribute("data-revoke"),{method:"DELETE"}).then(function(x){if(!x.ok){alert(friendlyErr("revoking the link",x.status,x.json));return;}loadAll();});};});(S.links||[]).forEach(function(l){if(l.revoked_at){var cell0=el.querySelector('tr[data-link="'+l.id+'"] .ev');if(cell0){cell0.textContent="\\u2014";}return;}api("/v1/orgs/"+S.org+"/share-links/"+l.id+"/events").then(function(x){var cell=el.querySelector('tr[data-link="'+l.id+'"] .ev');if(!cell){return;}if(!x.ok){cell.textContent="\\u2014";return;}var kinds={};(x.json.events||[]).forEach(function(e){kinds[e.kind]=(kinds[e.kind]||0)+1;});var parts=[];if(kinds.opened){parts.push(kinds.opened+" opened");}if(kinds.verified_file){parts.push(kinds.verified_file+" verified");}if(kinds.downloaded_pack||kinds.downloaded_witness){parts.push(((kinds.downloaded_pack||0)+(kinds.downloaded_witness||0))+" downloaded");}cell.textContent=parts.join(" \\u00B7 ")||"Not opened yet";});});var ta=document.getElementById("tab-link-all");if(ta){ta.onchange=function(){document.getElementById("tab-link-warn").style.display=ta.checked?"":"none";};}document.getElementById("tab-link-go").onclick=function(){createLink(document.getElementById("tab-link-cust").value,document.getElementById("tab-link-label").value.trim(),document.getElementById("tab-link-all").checked,document.getElementById("tab-link-msg"),document.getElementById("tab-link-out"),function(){loadAll();});};}`,
    `function renderKeys(){var el=document.getElementById("tab-keys");if(S.keys==="forbidden"||S.keys===null){el.innerHTML='<h3>Computers &amp; keys</h3><p class="warn">Only workspace owners can see computers and keys — ask an owner.</p>';return;}var rows=(S.keys||[]).map(function(k){var name=k.label||("\\u2026"+k.prefix);var btn=k.revoked_at?"":' <button type="button" class="btn btn-sec" data-revkey="'+esc(k.id)+'">Revoke</button>';var st=k.revoked_at?'<span class="pill bad">Revoked</span>':'<span class="pill ok">Live</span>';var last=k.last_used_at?localTime(k.last_used_at):"Never used";return '<tr><td>'+esc(name)+'</td><td class="small">'+esc(k.scopes)+'</td><td class="small">'+esc(localTime(k.created_at))+'</td><td class="small">'+esc(last)+'</td><td>'+st+btn+'</td></tr>';}).join("");el.innerHTML='<h3>Computers &amp; keys</h3><p class="small mut">Each connected computer holds a push-only key. Revoking cuts it off immediately.</p><div class="twrap"><table class="tbl"><thead><tr><th>Computer / key</th><th>Scopes</th><th>Added</th><th>Last used</th><th>Status</th></tr></thead><tbody>'+(rows||emptyRow(5,"No computers connected yet — finish guided step 2."))+'</tbody></table></div><details class="adv"><summary>Advanced: CI/automation key</summary><p class="small mut">For scripts and CI that cannot do the browser step. Raw keys are shown once.</p><label for="adv-label">Label</label><input id="adv-label" placeholder="ci-runner"><p><label><input type="checkbox" id="adv-push" checked style="width:auto"> push</label> <label><input type="checkbox" id="adv-read" style="width:auto"> read</label></p><p><button id="adv-go" type="button" class="btn btn-sec">Create automation key</button></p><p id="adv-msg" class="small" role="status"></p><div id="adv-out"></div><p class="small mut">Flag version for automation:</p><pre class="cmd" id="adv-cmd"></pre></details>';el.querySelectorAll("button[data-revkey]").forEach(function(btn){btn.onclick=function(){if(!confirm("Revoke this key? That computer immediately loses access.")){return;}api("/v1/orgs/"+S.org+"/api-keys/"+btn.getAttribute("data-revkey"),{method:"DELETE"}).then(function(x){if(!x.ok){alert(friendlyErr("revoking the key",x.status,x.json));return;}loadAll();});};});document.getElementById("adv-cmd").textContent="epi cloud login --url "+location.origin+" --org "+S.org+" --api-key <paste-key>";document.getElementById("adv-go").onclick=function(){var scopes=[];if(document.getElementById("adv-push").checked){scopes.push("push");}if(document.getElementById("adv-read").checked){scopes.push("read");}if(!scopes.length){document.getElementById("adv-msg").textContent="Pick at least one scope.";return;}var label=document.getElementById("adv-label").value.trim()||null;api("/v1/orgs/"+S.org+"/api-keys",{method:"POST",body:{scopes:scopes,label:label}}).then(function(x){if(!x.ok){document.getElementById("adv-msg").textContent=friendlyErr("creating the key",x.status,x.json);return;}document.getElementById("adv-msg").textContent="Key created. Raw key shown above \u2014 copy it, then click I\u2019ve saved it.";setReveal({kind:"key",secret:x.json.key,label:label||x.json.id||"automation key"});loadAll();});};}`,
    `boot();`,
  ].join("\n");
  return c.html(
    page("EPI Cloud — setup", `<span class="tag">Signed in</span>` + account, { script: script + "\n" + script2 }),
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
