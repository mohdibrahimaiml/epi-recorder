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
// create nothing. Signed-in view is the dashboard in the epilabs.org visual
// language (inline only, no tracking, no external requests): a 3-step guide
// for new owners, then tabs for runs, customers, share links, computers and
// team. One name per concept: workspace, customer, share link, computer.
// Share links point at https://epilabs.org, which hosts the trust page —
// never at the cloud origin.
// Trust page origin (hosts /t/:id). The cloud API returns relative trust
// URLs; only this human dashboard renders the absolute site link.
const TRUST_ORIGIN = "https://epilabs.org";

/** JSON for an inline <script>: never lets data close the script tag. */
function scriptJson(v: unknown): string {
  return JSON.stringify(v).replace(/</g, "\\u003c");
}

function landing(google: boolean): string {
  return (
    `<div class="hero"><span class="tag">Sealed evidence for AI runs</span>` +
    `<h1>Give your customers tamper-proof proof of what your AI agent did.</h1>` +
    `<p class="lede">EPI records each run of your AI agent, seals it, and has it independently witnessed. ` +
    `Your customer checks the evidence in their own browser.</p>` +
    `<div class="signin"><a class="btn btn-pri" href="/auth/github">Sign in with GitHub</a>` +
    (google ? `<a class="btn btn-sec" href="/auth/google">Sign in with Google</a>` : ``) +
    `</div></div>` +
    `<h2>How it works</h2>` +
    `<ol class="how">` +
    `<li><strong>Sign in</strong> and name your company. That’s your workspace.</li>` +
    `<li><strong>Run <code>epi demo</code> on your computer.</strong> It records a run, seals it and uploads it for your customer.</li>` +
    `<li><strong>Send your customer a share link.</strong> They open it in a browser — nothing to install — and see only their runs.</li>` +
    `</ol>` +
    `<div class="card"><strong>Free:</strong> 1 customer, 1 share link, 50 runs. ` +
    `<a href="https://epilabs.org/plans">See plans</a></div>` +
    `<p class="small mut">Want the details first? <a href="https://epilabs.org/how-it-works">How EPI works</a> · ` +
    `<a href="https://epilabs.org/verify/">Check an evidence file</a></p>`
  );
}

const DASH_SHELL =
  `<div id="ws"></div>` +
  `<div id="loading"><p class="mut">Loading your workspace…</p></div>` +
  `<div id="guide" style="display:none">` +
  `<h2>Get set up in 3 steps</h2>` +
  `<p class="lede">Three short steps. Each one unlocks the next, and this page updates by itself.</p>` +
  `<div id="steps"></div></div>` +
  `<div id="dash" style="display:none">` +
  `<p class="note ok" id="setup-done" style="display:none">✓ Setup complete. Add customers and share links any time from the tabs below.</p>` +
  `<div class="tabs" role="tablist">` +
  `<button type="button" class="tab active" data-tab="runs" role="tab" aria-selected="true">Runs</button>` +
  `<button type="button" class="tab" data-tab="customers" role="tab" aria-selected="false">Customers</button>` +
  `<button type="button" class="tab" data-tab="links" role="tab" aria-selected="false">Share links</button>` +
  `<button type="button" class="tab" data-tab="keys" role="tab" aria-selected="false">Computers &amp; keys</button>` +
  `<button type="button" class="tab" data-tab="team" role="tab" aria-selected="false">Team</button>` +
  `</div>` +
  `<div id="tab-runs" role="tabpanel"></div>` +
  `<div id="tab-customers" role="tabpanel" style="display:none"></div>` +
  `<div id="tab-links" role="tabpanel" style="display:none"></div>` +
  `<div id="tab-keys" role="tabpanel" style="display:none"></div>` +
  `<div id="tab-team" role="tabpanel" style="display:none"></div>` +
  `</div>`;

// Dashboard client. Plain ES5, no backticks or template interpolation
// inside (it is a raw string); every piece of user data goes through esc().
const DASH_JS = String.raw`var S={orgs:[],org:null,agents:[],keys:null,runs:[],inboxes:[],links:null,members:null,invites:null,loaded:false,sawGuide:false};
var MSG=null;
var REV={};
var timers=[];
var FREE_LIMITS={customers:1,shareLinks:1,evidenceFiles:50};
var PLANS_URL="https://epilabs.org/plans";
function byId(id){return document.getElementById(id);}
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(ch){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];});}
function localTime(iso){try{var d=new Date(iso);if(isNaN(d.getTime())){return iso||"";}return d.toLocaleString();}catch(e){return iso||"";}}
function dayWords(iso){var t=Date.parse(iso||"");if(isNaN(t)){return "";}var date=new Date(t).toLocaleDateString(undefined,{day:"numeric",month:"short",year:"numeric"});var days=Math.round((t-Date.now())/86400000);if(days>1){return date+" (in "+days+" days)";}if(days===1){return date+" (tomorrow)";}if(days===0){return date+" (today)";}if(days===-1){return date+" (yesterday)";}return date+" ("+(-days)+" days ago)";}
function isPast(iso){var t=Date.parse(iso||"");return !isNaN(t)&&t<Date.now();}
function rand4(){var a="abcdefghijkmnpqrstuvwxyz23456789",s="";for(var i=0;i<4;i++){s+=a.charAt(Math.floor(Math.random()*a.length));}return s;}
function slugify(n){var s=String(n||"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"").slice(0,40).replace(/-+$/,"");if(!s){return "team-"+rand4();}if(s.length<3){return s+"-team";}return s;}
function api(path,opts){opts=opts||{};return fetch(path,{method:opts.method||"GET",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:opts.body?JSON.stringify(opts.body):undefined}).then(function(r){return r.json().catch(function(){return {};}).then(function(j){return {ok:r.ok,status:r.status,json:j};});}).catch(function(){return {ok:false,status:0,json:{}};});}
function friendlyErr(action,status,j){var m=j&&j.error&&j.error.message;if(status===0){return "Couldn’t reach EPI Cloud — check your connection, then try again.";}if(status===401){return "Your sign-in expired — reload the page and sign in again.";}if(m){return m;}if(status===403){return "Only workspace owners can do this — ask an owner.";}if(status===404){return "This isn’t available yet — try again later.";}if(status===429){return "Too many tries — wait a minute, then try again.";}return "Something went wrong "+action+" — try again.";}
function isLimit(x){return x&&(x.status===402||(x.json&&x.json.error&&x.json.error.code==="plan_limit"));}
function errHtml(action,x){var h=esc(friendlyErr(action,x.status,x.json));var link='<a href="'+PLANS_URL+'" target="_blank" rel="noopener">epilabs.org/plans</a>';if(h.indexOf(PLANS_URL)>=0){h=h.split(PLANS_URL).join(link);}else if(isLimit(x)){h+=' <a href="'+PLANS_URL+'" target="_blank" rel="noopener">See plans and upgrade</a>';}return h;}
/* Messages: one at a time, keyed to the area under the button that caused
   it. They survive re-renders (paint() puts them back) until the next action. */
function say(area,cls,html){MSG={area:area,cls:cls,html:html};paintMsg();}
function clearMsg(){MSG=null;paintMsg();}
function paintMsg(){var els=document.querySelectorAll("[data-msg]");for(var i=0;i<els.length;i++){var e=els[i];if(MSG&&MSG.area===e.getAttribute("data-msg")){e.className="note "+MSG.cls;e.innerHTML=MSG.html;e.style.display="";}else{e.className="note";e.innerHTML="";e.style.display="none";}}}
function msgSlot(area){return '<div data-msg="'+esc(area)+'" role="status" style="display:none"></div>';}
/* One-time reveals (share link, rotated secret, CI key, invite link): shown
   inline under the button, kept across re-renders until Done, never again. */
function revSlot(area){return '<div data-rev="'+esc(area)+'"></div>';}
function setRev(area,html){REV[area]=html;paintRev();var el=document.querySelector('[data-rev="'+area+'"]');if(el&&el.scrollIntoView){el.scrollIntoView({behavior:"smooth",block:"center"});}}
function paintRev(){var els=document.querySelectorAll("[data-rev]");for(var i=0;i<els.length;i++){var a=els[i].getAttribute("data-rev");els[i].innerHTML=REV[a]?'<div class="reveal">'+REV[a]+'<p class="revdone"><button type="button" class="btn btn-sec btn-sm" data-done="'+esc(a)+'">Done</button> <span class="small mut">This is shown once. After Done it can’t be shown again.</span></p></div>':"";}}
function paint(){paintMsg();paintRev();}
var copyN=0;
function copyBox(text,cls){copyN++;var id="cp"+copyN;return '<div class="copyrow"><code id="'+id+'" class="'+(cls||"")+'">'+esc(text)+'</code><button type="button" class="btn btn-sec btn-sm" data-copyfrom="'+id+'">Copy</button></div>';}
function copyPre(text,label,cls){copyN++;var id="cp"+copyN;return '<div class="copyblock"><pre class="'+(cls||"cmd")+'" id="'+id+'">'+esc(text)+'</pre><button type="button" class="btn btn-sec btn-sm" data-copyfrom="'+id+'">'+esc(label||"Copy")+'</button></div>';}
function copyText(t,btn){function done(m){if(btn){var old=btn.getAttribute("data-label")||btn.textContent;btn.setAttribute("data-label",old);btn.textContent=m;setTimeout(function(){btn.textContent=old;},1800);}}if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(function(){done("Copied ✓");},function(){fallback();});return;}fallback();function fallback(){var ta=document.createElement("textarea");ta.value=t;document.body.appendChild(ta);ta.select();try{document.execCommand("copy");done("Copied ✓");}catch(e){done("Select and copy");}document.body.removeChild(ta);}}
document.addEventListener("click",function(ev){var t=ev.target;if(!t||!t.closest){return;}var c=t.closest("[data-copyfrom]");if(c){var src=byId(c.getAttribute("data-copyfrom"));if(src){copyText(src.textContent,c);}return;}var d=t.closest("[data-done]");if(d){var a=d.getAttribute("data-done");delete REV[a];clearMsg();paintRev();if(a==="guide-link"){S.sawGuide=true;loadAll();}}});
function stopTimers(){timers.forEach(function(t){clearInterval(t);});timers=[];}
function cur(){return (S.orgs||[]).filter(function(x){return x.id===S.org;})[0]||null;}
function role(){var o=cur();return (o&&o.role)||"owner";}
function isOwner(){return role()==="owner";}
function canAssign(){return role()==="owner"||role()==="member";}
function orgName(){var o=cur();return o?o.name:"";}
function keyList(){return Array.isArray(S.keys)?S.keys:null;}
function openInboxes(){return (S.inboxes||[]).filter(function(b){return !b.closed_at;});}
function custOptions(sel){return openInboxes().map(function(b){return '<option value="'+esc(b.id)+'"'+(b.id===sel?" selected":"")+'>'+esc(b.customer_label)+'</option>';}).join("");}
function sealBadge(check){if(check==="valid"){return '<span class="pill ok">Sealed ✓</span>';}if(check==="invalid"){return '<span class="pill bad">Seal broken ✗</span>';}return '<span class="pill">Not sealed</span>';}
function witBadge(st){if(st==="witnessed"){return '<span class="pill ok">Witnessed ✓</span>';}if(st==="different_version"){return '<span class="pill bad">Different copy</span>';}return '<span class="pill warn">Not witnessed</span>';}
function runTitle(r){if(r.goal){return esc(r.goal);}var w=String(r.workflow_id||"");if(w){return "Run "+esc(w.slice(0,8));}var h=String(r.claimed_sha256||"");return "Sealed run "+esc((h||String(r.id||"")).slice(0,8));}
function runSub(r){var h=String(r.claimed_sha256||"");var s=h?h.slice(0,8):"";return s?'<div class="small mut">Fingerprint '+esc(s)+'</div>':'';}
function agentName(id){var a=(S.agents||[]).filter(function(x){return x.id===id;})[0];return a?a.name:"";}
function inboxFor(label){return (S.inboxes||[]).filter(function(b){return b.customer_label===label;})[0]||null;}
function inboxLabel(id){var b=(S.inboxes||[]).filter(function(x){return x.id===id;})[0];return b?b.customer_label:"";}
function witHint(st,r){var cust=r&&r.agent_id?agentName(r.agent_id):"";var inb=cust?inboxFor(cust):null;if(st==="no_inbox"){return cust?"“"+cust+"” has no witness yet — run epi cloud login on that computer and pick "+cust+", then push the run again.":"Not linked to a customer yet — pick one below. New runs are witnessed once the computer is connected to a customer.";}if(st==="not_in_witness"){if(inb&&inb.closed_at){return cust+" is closed, so new runs aren’t witnessed. Reopen it in Customers to witness new runs.";}return "No witness stamp arrived for this file yet. On the computer that made it, run: epi witness flush — then push the file again. If epi witness flush says the secret was rejected, run epi cloud login on that computer first.";}if(st==="different_version"){return "A different copy of this run was witnessed, not this exact file.";}return "";}
function witSub(st,r){var h=witHint(st,r);return h?'<div class="small mut">'+esc(h)+'</div>':'';}
function runsForCustomer(label){return (S.runs||[]).filter(function(r){return r.agent_id&&agentName(r.agent_id)===label;});}
function scopeNames(scope){if(scope.inboxes==="all"){return ["All customers"];}return (scope.inboxes||[]).map(function(id){return inboxLabel(id)||"(removed customer)";});}
function planName(p){return {free:"Free",design_partner:"Design partner",startup:"Startup",growth:"Growth",enterprise:"Enterprise"}[p||"free"]||"Free";}
function n(x,one,many){return x+" "+(x===1?one:many);}
function limitsOf(o){if(o&&o.limits){return o.limits;}return (!o||!o.plan||o.plan==="free")?FREE_LIMITS:null;}
function usageOf(o){if(o&&o.usage){return o.usage;}return {customers:openInboxes().length,shareLinks:(S.links||[]).filter(function(l){return !l.revoked_at&&!isPast(l.expires_at);}).length,evidenceFiles:(S.runs||[]).length};}
function lim(v,one,many){return v==null?"unlimited "+many:n(v,one,many);}
function renderHead(){var o=cur();var el=byId("ws");if(!o){el.innerHTML="";return;}var L=limitsOf(o);var U=usageOf(o);var h='<div class="wshead"><div><span class="tag">Workspace</span><h1 class="wsname">'+esc(o.name)+'</h1></div>';if((S.orgs||[]).length>1){h+='<div class="wspick"><label for="org-pick" class="small mut">Switch workspace</label><select id="org-pick">'+S.orgs.map(function(x){return '<option value="'+esc(x.id)+'"'+(x.id===S.org?" selected":"")+'>'+esc(x.name)+'</option>';}).join("")+'</select></div>';}h+='</div>';var unlim=L&&L.customers==null&&L.shareLinks==null&&L.evidenceFiles==null;var plan='<strong>Plan: '+esc(planName(o.plan))+'</strong>';if(unlim){plan+=' — unlimited';}else if(L){plan+=' — '+esc(lim(L.customers,"customer","customers")+" · "+lim(L.shareLinks,"share link","share links")+" · "+lim(L.evidenceFiles,"run","runs"));}var use="";if(L&&U){var parts=[];[["customers","customers"],["shareLinks","share links"],["evidenceFiles","runs"]].forEach(function(p){var u=U[p[0]];if(u==null){return;}var l=L[p[0]];var full=l!=null&&u>=l;parts.push('<span class="'+(full?"full":"")+'">'+esc(u+(l!=null?" of "+l:"")+" "+p[1])+'</span>');});use=parts.join(" · ");}h+='<div class="planbar small"><div>'+plan+'</div>'+(use?'<div class="mut">Using '+use+'</div>':'')+(unlim?"":'<a class="upg" href="'+PLANS_URL+'" target="_blank" rel="noopener">Upgrade</a>')+'</div>';var r=role();if(r==="member"){h+='<p class="small mut">You’re a <strong>member</strong> of this workspace: you can see runs and customers and assign runs. Owners create share links and manage computers.</p>';}else if(r==="viewer"){h+='<p class="small mut">You have <strong>view-only</strong> access to this workspace. Ask an owner if you need to change something.</p>';}el.innerHTML=h;var pick=byId("org-pick");if(pick){pick.onchange=function(){S.org=this.value;MSG=null;REV={};loadAll();};}}
function boot(){api("/v1/orgs").then(function(x){S.orgs=(x.ok&&x.json.orgs)||[];if(!x.ok&&x.status!==0){byId("loading").innerHTML='<p class="err">'+errHtml("loading your workspaces",x)+'</p>';return;}if(!S.orgs.length){S.org=null;render();return;}S.org=S.orgs[0].id;loadAll();});}
function loadAll(){stopTimers();var id=S.org;if(!id){render();return;}var o="/v1/orgs/"+id;Promise.all([api(o+"/agents"),isOwner()?api(o+"/api-keys"):Promise.resolve({ok:false,status:403,json:{}}),api(o+"/artifacts"),api(o+"/inboxes"),isOwner()?api(o+"/share-links"):Promise.resolve({ok:false,status:403,json:{}}),role()==="viewer"?Promise.resolve({ok:false,status:403,json:{}}):api(o+"/members"),isOwner()?api(o+"/invites"):Promise.resolve({ok:false,status:403,json:{}}),api("/v1/orgs")]).then(function(rs){if(id!==S.org){return;}S.agents=(rs[0].ok&&rs[0].json.agents)||[];S.keys=rs[1].ok?(rs[1].json.keys||[]):null;S.runs=(rs[2].ok&&rs[2].json.artifacts)||[];S.inboxes=(rs[3].ok&&rs[3].json.inboxes)||[];S.links=rs[4].ok?(rs[4].json.links||[]):null;S.members=rs[5].ok?(rs[5].json.members||[]):null;S.membersStatus=rs[5].status;S.invites=rs[6].ok?(rs[6].json.invites||[]):null;if(rs[7].ok&&rs[7].json.orgs&&rs[7].json.orgs.length){S.orgs=rs[7].json.orgs;}S.loaded=true;render();});}
function milestones(){var k=keyList();return {org:!!S.org,key:k?k.length>0:true,run:S.runs.length>0,customer:S.inboxes.length>0,link:!!(S.links&&S.links.length)};}
function currentStepRaw(m){if(!m.org){return 1;}if(!m.key||!m.customer){return 2;}if(!m.run||!m.link){return 3;}return 4;}
function currentStep(m){var s=currentStepRaw(m);if(REV["guide-link"]&&s>3){return 3;}return s;}
function render(){stopTimers();byId("loading").style.display="none";renderHead();var m=milestones();var step=currentStep(m);if(S.org&&!isOwner()){step=4;}if(step>3){renderDash();paint();return;}S.sawGuide=true;byId("dash").style.display="none";byId("guide").style.display="";renderGuide(m,step);paint();}
function stepShell(n,title,state,inner){var mark=state==="done"?'<span class="mark done">✓ Done</span>':(state==="current"?'<span class="mark">Step '+n+' of 3</span>':'<span class="mark mut">Next</span>');return '<div class="step '+state+'"><div class="stephead"><span class="stepnum">'+n+'</span><strong>'+title+'</strong>'+mark+'</div><div class="stepbody">'+inner+'</div></div>';}
function renderGuide(m,step){var h="";h+=stepShell(1,"Name your company",step>1?"done":"current",stepHtml1(step===1,m));h+=stepShell(2,"Connect your computer and pick a customer",(m.key&&m.customer)?"done":(step===2?"current":"locked"),stepHtml2(step===2,m));h+=stepShell(3,"Record your first run and share it",(m.run&&m.link&&!REV["guide-link"])?"done":(step===3?"current":"locked"),stepHtml3(step===3,m));byId("steps").innerHTML=h;wireGuide(step,m);if(step===2){timers.push(setInterval(function(){loadAll();},5000));}if(step===3&&!m.run){timers.push(setInterval(function(){api("/v1/orgs/"+S.org+"/artifacts").then(function(x){if(x.ok&&(x.json.artifacts||[]).length){loadAll();}});},5000));}}
function stepHtml1(active,m){if(!active){return m.org?'<p class="small">Workspace: <strong>'+esc(orgName())+'</strong></p>':'';}return '<p>What’s your company called? This names your workspace.</p><label for="org-name">Company name</label><input id="org-name" placeholder="Acme AI" autocomplete="organization" maxlength="120"><details class="adv"><summary>Advanced: edit the short web name</summary><label for="org-slug">Short web name (lowercase letters, numbers, dashes)</label><input id="org-slug" placeholder="acme-ai" maxlength="50"></details><p><button id="org-go" type="button" class="btn btn-pri">Create workspace</button></p>'+msgSlot("org");}
function stepHtml2(active,m){var k=keyList();if(!active){return '<p class="small">'+(k?n(k.length,"computer","computers")+" connected · ":"")+n(S.inboxes.length,"customer","customers")+'.</p>';}var origin=location.origin;var login="epi cloud login"+(origin==="https://cloud.epilabs.org"?"":" --url "+origin);var st;if(m.key&&k&&k.length&&!m.customer){st='<span class="ok-t">✓ Computer connected — now pick a customer.</span> Run <code>epi cloud login</code> again and type the customer’s name (for example <em>Acme Bank</em>) on the “Connect this computer” page.';}else{st='Waiting for your computer… this page updates by itself.';}return '<p>On your computer, open a terminal and run these two commands:</p>'+copyPre("pip install -U epi-recorder")+copyPre(login)+'<p class="small">The second command shows a short code. Type it at <a href="/auth/device" target="_blank" rel="noopener">Connect this computer</a> and write the name of the customer this evidence is for. Nothing secret to copy — the rest happens automatically. Needs epi-recorder 4.6.2 or newer (check with <code>epi --version</code>).</p><p id="s2-msg" class="small" role="status">'+st+'</p>';}
function stepHtml3(active,m){if(!active){return m.run?'<p class="small">'+n(S.runs.length,"run","runs")+' received.</p>':'';}var s3msg='Waiting for the first run… this page updates by itself.';if((S.runs||[]).length){var l=S.runs[0];var nm=(l&&(l.goal||l.workflow_id||l.id))||"run";s3msg='✓ '+n(S.runs.length,"run","runs")+' received — latest: '+esc(nm);}var first=openInboxes()[0];var shareH;if(REV["guide-link"]){shareH='<h3>Share it with your customer</h3>'+msgSlot("guide-link")+revSlot("guide-link");}else if(m.link){shareH='<p class="ok-t">\u2713 Share link created. Once the first run arrives, you\u2019re done.</p>';}else{shareH='<h3>Share it with your customer</h3><p class="small">The share link shows <strong>only this customer\u2019s</strong> runs. Your customer opens it in a browser \u2014 nothing to install.</p><label for="link-cust">Customer</label><select id="link-cust">'+custOptions(first?first.id:"")+'</select><label for="link-label">Link name (only you see this)</label><input id="link-label" placeholder="'+esc((first?first.customer_label:"Acme Bank")+" review")+'"><p><button id="link-go" type="button" class="btn btn-pri">Create share link</button></p>'+msgSlot("guide-link")+revSlot("guide-link");}return '<p>On your computer, run:</p>'+copyPre("epi demo")+'<p class="small">One command records, seals and uploads a sample run for your customer. Nothing to paste.</p><p id="s3-msg" class="small" role="status">'+s3msg+'</p>'+shareH;}
function wireGuide(step,m){var nm=byId("org-name");if(nm){var sl=byId("org-slug");var touched=false;sl.oninput=function(){touched=true;};nm.oninput=function(){if(!touched){sl.value=nm.value.trim()?slugify(nm.value):"";}};byId("org-go").onclick=function(){createOrg(nm.value.trim(),sl.value.trim()||slugify(nm.value),!touched);};nm.onkeydown=function(e){if(e.key==="Enter"){byId("org-go").click();}};}var lg=byId("link-go");if(lg){lg.onclick=function(){createLink(byId("link-cust").value,byId("link-label").value.trim(),false,"guide-link",lg);};}}
function createOrg(name,slug,auto){if(!name){say("org","err","Type your company name first.");return;}clearMsg();var btn=byId("org-go");btn.disabled=true;say("org","","Creating your workspace…");api("/v1/orgs",{method:"POST",body:{name:name,slug:slug}}).then(function(x){if(!x.ok&&x.status===409&&auto){return api("/v1/orgs",{method:"POST",body:{name:name,slug:slug.slice(0,44)+"-"+rand4()}});}return x;}).then(function(x){btn.disabled=false;if(!x.ok){say("org","err",errHtml("creating the workspace",x));return;}clearMsg();S.orgs.push({id:x.json.id,name:x.json.name,slug:x.json.slug,plan:x.json.plan||"free",role:"owner"});S.org=x.json.id;loadAll();});}
function resolveAgentId(inboxId){var inb=(S.inboxes||[]).filter(function(b){return b.id===inboxId;})[0];if(!inb){return Promise.resolve(null);}var a=(S.agents||[]).filter(function(x){return x.name===inb.customer_label;})[0];if(a){return Promise.resolve(a.id);}return api("/v1/orgs/"+S.org+"/inboxes/by-customer",{method:"POST",body:{customer_label:inb.customer_label}}).then(function(x){return x.ok?(x.json.agent_id||null):null;});}
function shareMessage(cust,url){return "Hi — here is our sealed, independently witnessed evidence for "+cust+":\n"+url+"\n\nIt opens in your browser, nothing to install. The part after # is the key — please don’t share the link further.";}
function createLink(inboxId,label,all,area,btn){clearMsg();if(!all&&!inboxId){say(area,"err","Add a customer first — a share link shows one customer’s runs.");return;}var cust=all?"all customers":inboxLabel(inboxId);var name=label||((all?"All customers":cust)+" review");if(btn){btn.disabled=true;}say(area,"","Creating the share link…");(all?Promise.resolve("all"):resolveAgentId(inboxId)).then(function(aid){if(!aid){if(btn){btn.disabled=false;}say(area,"err","Couldn’t find "+esc(cust)+" — reload the page and try again.");return;}var agent={id:aid};var scope=all?{agents:"all",inboxes:"all"}:{agents:[agent.id],inboxes:[inboxId]};api("/v1/orgs/"+S.org+"/share-links",{method:"POST",body:{label:name,scope:scope}}).then(function(x){if(btn){btn.disabled=false;}if(!x.ok){say(area,"err",errHtml("creating the share link",x));return;}clearMsg();var url=TRUST_ORIGIN+"/t/"+x.json.id+"#k="+x.json.token;if(area==="guide-link"){REV[area]="\u2026";render();}setRev(area,'<p class="ok-t"><strong>✓ Share link for '+esc(cust)+' is ready.</strong></p><label class="small">The link</label>'+copyBox(url,"wrap-anywhere")+'<p class="small"><a href="'+esc(url)+'" target="_blank" rel="noopener">Open it as your customer will see it</a></p><label class="small">Ready-to-send message</label>'+copyPre(shareMessage(all?orgName():cust,url),"Copy message","msgbox"));loadAll();});});}
function renderDash(){byId("guide").style.display="none";byId("dash").style.display="";var banner=byId("setup-done");var show=false;if(S.sawGuide&&S.org){var k="epi_setup_banner_"+S.org;try{if(!localStorage.getItem(k)){show=true;localStorage.setItem(k,"1");}}catch(e){show=true;}S.sawGuide=false;S.bannerFor=show?S.org:S.bannerFor;}banner.style.display=(S.bannerFor&&S.bannerFor===S.org)?"":"none";var vis={team:role()!=="viewer",links:isOwner(),keys:isOwner()};var act=document.querySelector("button.tab.active");if(act&&vis[act.getAttribute("data-tab")]===false){document.querySelector('button.tab[data-tab="runs"]').click();}Object.keys(vis).forEach(function(t){var b=document.querySelector('button.tab[data-tab="'+t+'"]');if(b){b.style.display=vis[t]?"":"none";}});renderRuns();renderCustomers();renderLinks();renderKeys();renderTeam();}
document.querySelectorAll("button.tab").forEach(function(b){b.onclick=function(){document.querySelectorAll("button.tab").forEach(function(x){x.classList.remove("active");x.setAttribute("aria-selected","false");});b.classList.add("active");b.setAttribute("aria-selected","true");["runs","customers","links","keys","team"].forEach(function(t){byId("tab-"+t).style.display=(t===b.getAttribute("data-tab"))?"":"none";});};});
function emptyRow(cols,msg){return '<tr class="empty"><td colspan="'+cols+'">'+msg+'</td></tr>';}
function td(label,inner,cls){return '<td data-l="'+esc(label)+'"'+(cls?' class="'+cls+'"':'')+'>'+inner+'</td>';}
function assignRun(id,label){clearMsg();api("/v1/orgs/"+S.org+"/artifacts/"+id+"/agent",{method:"PATCH",body:{agent:label}}).then(function(x){if(!x.ok){say("runs","err",errHtml("assigning the run",x));return;}say("runs","ok","Run assigned to "+esc(label)+".");loadAll();});}
function renderRuns(){var el=byId("tab-runs");var opts=openInboxes().map(function(b){return '<option value="'+esc(b.customer_label)+'">'+esc(b.customer_label)+'</option>';}).join("");var rows=(S.runs||[]).map(function(r){var cust=(r.agent_id&&agentName(r.agent_id))||"Unassigned";var assign="";if(!r.agent_id&&opts&&canAssign()){assign='<div class="acts"><select data-assign="'+esc(r.id)+'" aria-label="Customer">'+opts+'</select><button type="button" class="btn btn-sec btn-sm" data-assignbtn="'+esc(r.id)+'">Assign</button></div>';}return '<tr>'+td("Run",'<strong>'+runTitle(r)+'</strong>'+runSub(r))+td("Seal",sealBadge(r.signature_check))+td("Witness",witBadge(r.witness_status)+witSub(r.witness_status,r))+td("Customer",esc(cust)+assign)+td("Received",esc(localTime(r.uploaded_at||r.sealed_at||"")),"small")+'</tr>';}).join("");el.innerHTML='<h2>Runs</h2><p class="small mut">Runs your computers sent here. Each run shows whether it was sealed and independently witnessed.</p>'+msgSlot("runs")+'<div class="twrap"><table class="tbl"><thead><tr><th>Run</th><th>Seal</th><th>Witness</th><th>Customer</th><th>Received</th></tr></thead><tbody>'+(rows||emptyRow(5,"No runs yet. On a connected computer, run <code>epi demo</code>."))+'</tbody></table></div>';el.querySelectorAll("button[data-assignbtn]").forEach(function(btn){btn.onclick=function(){var id=btn.getAttribute("data-assignbtn");var sel=el.querySelector('select[data-assign="'+id+'"]');var label=sel?sel.value:"";if(!label){return;}assignRun(id,label);};});}
function rotateSecret(inboxId,label){clearMsg();if(!confirm("Rotate the witness secret for "+label+"?\n\nComputers recording for "+label+" stop being witnessed until someone runs “epi cloud login” on each of them and picks "+label+". Runs already witnessed stay valid.")){return;}var area="cust-"+inboxId;say(area,"","Rotating…");api("/v1/orgs/"+S.org+"/inboxes/"+inboxId+"/rotate",{method:"POST"}).then(function(x){if(!x.ok){say(area,"err",errHtml("rotating the secret",x));return;}clearMsg();setRev(area,'<p class="ok-t"><strong>✓ New witness secret for '+esc(label)+'.</strong> The old one no longer works. Runs already witnessed stay valid.</p><p>On each computer for '+esc(label)+', run:</p>'+copyPre("epi cloud login")+'<p class="small">and pick <strong>'+esc(label)+'</strong> on the “Connect this computer” page. That’s all — nothing to paste.</p><details class="adv"><summary>Advanced: CI or manual setup</summary><p class="small mut">Only for CI jobs or computers that can’t do the browser step. Put these in that environment’s secret settings:</p>'+copyPre("EPI_WITNESS_URL="+x.json.url+"\nEPI_WITNESS_SECRET="+x.json.secret,"Copy both")+'</details>');loadAll();});}
function closeCustomer(inboxId,label){clearMsg();if(!confirm("Close "+label+"?\n\nComputers recording for "+label+" stop being witnessed. Past runs and share links stay.")){return;}var area="cust-"+inboxId;api("/v1/orgs/"+S.org+"/inboxes/"+inboxId+"/close",{method:"POST"}).then(function(x){if(!x.ok){say(area,"err",errHtml("closing the customer",x));return;}say(area,"ok",esc(label)+" is closed. You can reopen it any time.");loadAll();});}
function reopenCustomer(inboxId,label){clearMsg();var area="cust-"+inboxId;say(area,"","Reopening…");api("/v1/orgs/"+S.org+"/inboxes/"+inboxId+"/reopen",{method:"POST"}).then(function(x){if(!x.ok){say(area,"err",errHtml("reopening the customer",x));return;}say(area,"ok",esc(label)+' is open again. Computers recording for it need <code>epi cloud login</code> (pick '+esc(label)+') before new runs are witnessed.');loadAll();});}
function createCustomer(label,btn){clearMsg();if(!label){say("cust-add","err","Type the customer’s name first.");return;}if(btn){btn.disabled=true;}say("cust-add","","Adding "+esc(label)+"…");api("/v1/orgs/"+S.org+"/inboxes/by-customer",{method:"POST",body:{customer_label:label}}).then(function(x){if(btn){btn.disabled=false;}if(!x.ok){say("cust-add","err",errHtml("adding the customer",x));return;}var nm=x.json.label||label;if(x.json.created===false){say("cust-add","ok",esc(nm)+" already exists — nothing changed.");}else{say("cust-add","ok",'✓ '+esc(nm)+' added. To record for '+esc(nm)+', run <code>epi cloud login</code> on a computer and pick '+esc(nm)+'. No secrets to copy.');}loadAll();});}
function renderCustomers(){var el=byId("tab-customers");var own=isOwner();var rows=(S.inboxes||[]).map(function(b){var c=runsForCustomer(b.customer_label).length;var st=b.closed_at?'<span class="pill">Closed</span>':'<span class="pill ok">Open</span>';var acts="";if(own){acts=b.closed_at?'<button type="button" class="btn btn-sec btn-sm" data-reopen="'+esc(b.id)+'" data-label="'+esc(b.customer_label)+'">Reopen</button>':'<button type="button" class="btn btn-sec btn-sm" data-rotate="'+esc(b.id)+'" data-label="'+esc(b.customer_label)+'">Rotate secret</button><button type="button" class="btn btn-sec btn-sm" data-close="'+esc(b.id)+'" data-label="'+esc(b.customer_label)+'">Close</button>';}return '<tr>'+td("Customer",'<strong>'+esc(b.customer_label)+'</strong>')+td("Runs",String(c))+td("Added",esc(dayWords(b.created_at)),"small")+td("Status",st+(acts?'<div class="acts">'+acts+'</div>':''))+'</tr><tr class="sub"><td colspan="4">'+msgSlot("cust-"+b.id)+revSlot("cust-"+b.id)+'</td></tr>';}).join("");var add=own?'<div class="card"><h3>Add a customer</h3><p class="small mut">Each customer gets their own witness. Their runs never mix with another customer’s.</p><label for="tab-cust-name">Customer name</label><input id="tab-cust-name" placeholder="Acme Bank" maxlength="120"><p><button id="tab-cust-go" type="button" class="btn btn-pri">Add customer</button></p>'+msgSlot("cust-add")+'</div>':'';el.innerHTML='<h2>Customers</h2><p class="small mut">Who your evidence is for. Closing a customer stops new runs being witnessed for them; past runs and share links stay.</p><div class="twrap"><table class="tbl"><thead><tr><th>Customer</th><th>Runs</th><th>Added</th><th>Status</th></tr></thead><tbody>'+(rows||emptyRow(4,own?"No customers yet — add one below.":"No customers yet."))+'</tbody></table></div>'+add;el.querySelectorAll("button[data-close]").forEach(function(btn){btn.onclick=function(){closeCustomer(btn.getAttribute("data-close"),btn.getAttribute("data-label"));};});el.querySelectorAll("button[data-reopen]").forEach(function(btn){btn.onclick=function(){reopenCustomer(btn.getAttribute("data-reopen"),btn.getAttribute("data-label"));};});el.querySelectorAll("button[data-rotate]").forEach(function(btn){btn.onclick=function(){rotateSecret(btn.getAttribute("data-rotate"),btn.getAttribute("data-label"));};});var go=byId("tab-cust-go");if(go){go.onclick=function(){createCustomer(byId("tab-cust-name").value.trim(),go);};}}
function linkActivity(el,l){api("/v1/orgs/"+S.org+"/share-links/"+l.id+"/events").then(function(x){var cell=el.querySelector('tr[data-link="'+l.id+'"] .ev');if(!cell){return;}if(!x.ok){cell.textContent="—";return;}var kinds={};(x.json.events||[]).forEach(function(e){kinds[e.kind]=(kinds[e.kind]||0)+1;});var parts=[];if(kinds.opened){parts.push("Opened "+(kinds.opened===1?"once":kinds.opened+" times"));}if(kinds.verified_file){parts.push(n(kinds.verified_file,"file checked","files checked"));}var dl=(kinds.downloaded_pack||0)+(kinds.downloaded_witness||0);if(dl){parts.push(n(dl,"download","downloads"));}cell.textContent=parts.join(" · ")||"Not opened yet";});}
function renderLinks(){var el=byId("tab-links");if(!isOwner()||S.links===null){el.innerHTML='<h2>Share links</h2><p class="note">Only workspace owners create and see share links — ask an owner to send one to your customer.</p>';return;}var rows=(S.links||[]).map(function(l){var scope={};try{scope=JSON.parse(l.scope);}catch(e){scope={agents:"all",inboxes:"all"};}var expired=!l.revoked_at&&isPast(l.expires_at);var st=l.revoked_at?'<span class="pill bad">Revoked</span>':(expired?'<span class="pill warn">Expired</span>':'<span class="pill ok">Live</span>');var acts="";if(!l.revoked_at&&!expired){acts='<button type="button" class="btn btn-sec btn-sm" data-revoke="'+esc(l.id)+'" data-label="'+esc(l.label)+'">Revoke</button>';}var oneInbox=(scope.inboxes&&scope.inboxes!=="all"&&scope.inboxes.length===1)?scope.inboxes[0]:"";if(expired||l.revoked_at){if(!oneInbox||openInboxes().some(function(b){return b.id===oneInbox;})){acts+='<button type="button" class="btn btn-sec btn-sm" data-again="'+esc(oneInbox)+'">Create a new link</button>';}}var exp=l.revoked_at?"—":(expired?"Expired "+dayWords(l.expires_at):dayWords(l.expires_at));return '<tr data-link="'+esc(l.id)+'">'+td("Link",'<strong>'+esc(l.label)+'</strong>')+td("For",esc(scopeNames(scope).join(", ")))+td("Expires",esc(exp),"small")+td("Activity",l.revoked_at?"—":"Loading…","small ev")+td("Status",st+(acts?'<div class="acts">'+acts+'</div>':''))+'</tr><tr class="sub"><td colspan="5">'+msgSlot("link-"+l.id)+'</td></tr>';}).join("");el.innerHTML='<h2>Share links</h2><p class="small mut">Send a share link to your customer. It opens in their browser and shows only that customer’s runs, sealed and witnessed.</p><div class="twrap"><table class="tbl"><thead><tr><th>Link</th><th>For</th><th>Expires</th><th>Activity</th><th>Status</th></tr></thead><tbody>'+(rows||emptyRow(5,"No share links yet — create one below."))+'</tbody></table></div><div class="card" id="new-link"><h3>Create a share link</h3>'+linkLimitNote()+'<label for="tab-link-cust">Customer</label><select id="tab-link-cust">'+custOptions(S.linkPick||"")+'</select><label for="tab-link-label">Link name (only you see this)</label><input id="tab-link-label" placeholder="Acme Bank review" maxlength="120"><details class="adv"><summary>Advanced: one link for all customers</summary><p><label class="inline"><input type="checkbox" id="tab-link-all"> Show <strong>every</strong> customer’s runs on this link</label></p><p class="warn small">Anyone with this link sees every customer’s runs. Use it only for your own team’s review.</p></details><p><button id="tab-link-go" type="button" class="btn btn-pri">Create share link</button></p>'+msgSlot("tab-link")+revSlot("tab-link")+'</div>';el.querySelectorAll("button[data-revoke]").forEach(function(btn){btn.onclick=function(){clearMsg();var id=btn.getAttribute("data-revoke");if(!confirm("Revoke “"+btn.getAttribute("data-label")+"”?\n\nAnyone using this link loses access right away.")){return;}api("/v1/orgs/"+S.org+"/share-links/"+id,{method:"DELETE"}).then(function(x){if(!x.ok){say("link-"+id,"err",errHtml("revoking the link",x));return;}say("tab-link","ok","Link revoked.");loadAll();});};});el.querySelectorAll("button[data-again]").forEach(function(btn){btn.onclick=function(){var v=btn.getAttribute("data-again");var sel=byId("tab-link-cust");if(v&&sel){sel.value=v;}var card=byId("new-link");if(card&&card.scrollIntoView){card.scrollIntoView({behavior:"smooth",block:"center"});}var inp=byId("tab-link-label");if(inp){inp.focus();}};});(S.links||[]).forEach(function(l){if(!l.revoked_at){linkActivity(el,l);}});document.getElementById("tab-link-go").onclick=function(){S.linkPick=byId("tab-link-cust").value;createLink(byId("tab-link-cust").value,byId("tab-link-label").value.trim(),byId("tab-link-all").checked,"tab-link",byId("tab-link-go"));};}
function linkLimitNote(){var o=cur();var L=limitsOf(o);var U=usageOf(o);if(!L||L.shareLinks==null||!U||U.shareLinks==null||U.shareLinks<L.shareLinks){return "";}return '<p class="note small">Your plan\u2019s '+n(L.shareLinks,"share link is","share links are")+' in use. Revoke one above, or <a href="'+PLANS_URL+'" target="_blank" rel="noopener">upgrade</a> for more. Expired links don\u2019t count.</p>';}
function scopeWords(s){var p=String(s||"").split(",");var w=[];if(p.indexOf("push")>=0){w.push("Can upload runs");}if(p.indexOf("read")>=0){w.push("Can read runs");}return w.join(" · ")||"—";}
function renderKeys(){var el=byId("tab-keys");var k=keyList();if(!isOwner()||k===null){el.innerHTML='<h2>Computers</h2><p class="note">Only workspace owners can see and manage connected computers — ask an owner.</p>';return;}var hasCust=k.some(function(x){return !!x.customer_label;});var rows=k.map(function(x){var name=x.label||"Unnamed computer";var act=x.revoked_at?"":'<div class="acts"><button type="button" class="btn btn-sec btn-sm" data-revkey="'+esc(x.id)+'" data-label="'+esc(name)+'">Revoke</button></div>';var st=x.revoked_at?'<span class="pill bad">Revoked</span>':'<span class="pill ok">Connected</span>';return '<tr>'+td("Computer",'<strong>'+esc(name)+'</strong><div class="small mut">'+esc(scopeWords(x.scopes))+'</div>')+(hasCust?td("Records for",esc(x.customer_label||"—")):'')+td("Last used",esc(x.last_used_at?dayWords(x.last_used_at):"Never"),"small")+td("Status",st+act)+'</tr><tr class="sub"><td colspan="'+(hasCust?4:3)+'">'+msgSlot("key-"+x.id)+'</td></tr>';}).join("");var cols=hasCust?4:3;var ciOpen=!!(REV.ci||(MSG&&MSG.area==="ci"));var login="epi cloud login"+(location.origin==="https://cloud.epilabs.org"?"":" --url "+location.origin);el.innerHTML='<h2>Computers</h2><p class="small mut">Computers that upload runs to this workspace. To add one, run <code>'+esc(login)+'</code> on it. Revoking cuts a computer off right away.</p><div class="twrap"><table class="tbl"><thead><tr><th>Computer</th>'+(hasCust?'<th>Records for</th>':'')+'<th>Last used</th><th>Status</th></tr></thead><tbody>'+(rows||emptyRow(cols,"No computers connected yet — run <code>"+esc(login)+"</code> on one."))+'</tbody></table></div><details class="adv" id="ci-adv"'+(ciOpen?" open":"")+'><summary>Advanced: key for CI or automation</summary><p class="small mut">Only for CI jobs and scripts that can’t do the browser step. Normal computers should use <code>epi cloud login</code>.</p><label for="adv-label">Name</label><input id="adv-label" placeholder="github-actions" maxlength="80"><label for="adv-cust">Records for customer</label><select id="adv-cust"><option value="">No customer</option>'+openInboxes().map(function(b){return '<option value="'+esc(b.customer_label)+'">'+esc(b.customer_label)+'</option>';}).join("")+'</select><p><label class="inline"><input type="checkbox" id="adv-push" checked> Can upload runs</label> <label class="inline"><input type="checkbox" id="adv-read"> Can read runs</label></p><p><button id="adv-go" type="button" class="btn btn-sec">Create CI key</button></p>'+msgSlot("ci")+revSlot("ci")+'</details>';el.querySelectorAll("button[data-revkey]").forEach(function(btn){btn.onclick=function(){clearMsg();var id=btn.getAttribute("data-revkey");if(!confirm("Revoke “"+btn.getAttribute("data-label")+"”?\n\nThat computer can no longer upload runs. Runs it already sent stay.")){return;}api("/v1/orgs/"+S.org+"/api-keys/"+id,{method:"DELETE"}).then(function(x){if(!x.ok){say("key-"+id,"err",errHtml("revoking the computer",x));return;}loadAll();});};});byId("adv-go").onclick=function(){clearMsg();var scopes=[];if(byId("adv-push").checked){scopes.push("push");}if(byId("adv-read").checked){scopes.push("read");}if(!scopes.length){say("ci","err","Tick at least one: upload or read.");return;}var label=byId("adv-label").value.trim();var cust=byId("adv-cust").value;var body={scopes:scopes};if(label){body.label=label;}if(cust){body.customer_label=cust;}api("/v1/orgs/"+S.org+"/api-keys",{method:"POST",body:body}).then(function(x){if(!x.ok){say("ci","err",errHtml("creating the key",x));return;}var env="EPI_CLOUD_URL="+location.origin+"\nEPI_CLOUD_ORG="+S.org+"\nEPI_CLOUD_API_KEY="+x.json.key;if(x.json.witness_url&&x.json.witness_secret){env+="\nEPI_WITNESS_URL="+x.json.witness_url+"\nEPI_WITNESS_SECRET="+x.json.witness_secret;}setRev("ci",'<p class="ok-t"><strong>✓ CI key created.</strong></p><h3 class="small">For CI only</h3><p class="small mut">Add these as secret environment variables in your CI settings. Never commit them to code.</p>'+copyPre(env,"Copy all")+(cust&&!x.json.witness_secret?'<p class="small mut">Runs from this key are tagged to '+esc(cust)+'.</p>':''));loadAll();});};}
function roleWords(r){return {owner:"Owner",member:"Member",viewer:"Viewer"}[r]||r;}
function inviteMessage(email,url,exp){return "Hi — I’ve added you to our "+orgName()+" workspace on EPI Cloud.\nSign in with "+email+" here:\n"+url+"\n\nThe link works once and expires "+exp+".";}
function renderTeam(){var el=byId("tab-team");var own=isOwner();if(S.members===null){el.innerHTML='<h2>Team</h2><p class="note">Only owners and members can see the team.</p>';return;}var owners=S.members.filter(function(m){return m.role==="owner";}).length;var rows=S.members.map(function(m){var act="";if(own&&!(m.role==="owner"&&owners<=1)){act='<div class="acts"><button type="button" class="btn btn-sec btn-sm" data-rmuser="'+esc(m.user_id)+'" data-label="'+esc(m.email)+'">Remove</button></div>';}return '<tr>'+td("Person",'<strong>'+esc(m.email||"—")+'</strong>')+td("Role",esc(roleWords(m.role))+act)+'</tr><tr class="sub"><td colspan="2">'+msgSlot("mem-"+m.user_id)+'</td></tr>';}).join("");var h='<h2>Team</h2><p class="small mut">People who can sign in to this workspace.</p><div class="twrap"><table class="tbl"><thead><tr><th>Person</th><th>Role</th></tr></thead><tbody>'+(rows||emptyRow(2,"Just you so far."))+'</tbody></table></div>';if(own){var inv=(S.invites||[]).map(function(i){return '<tr>'+td("Invited",'<strong>'+esc(i.email)+'</strong>')+td("Role",esc(roleWords(i.role)))+td("Expires",esc(dayWords(i.expires_at)),"small")+td("",'<div class="acts"><button type="button" class="btn btn-sec btn-sm" data-rminv="'+esc(i.id)+'" data-label="'+esc(i.email)+'">Cancel invite</button></div>')+'</tr><tr class="sub"><td colspan="4">'+msgSlot("inv-"+i.id)+'</td></tr>';}).join("");if(inv){h+='<h3>Waiting to join</h3><div class="twrap"><table class="tbl"><thead><tr><th>Invited</th><th>Role</th><th>Expires</th><th></th></tr></thead><tbody>'+inv+'</tbody></table></div>';}h+='<div class="card"><h3>Invite someone</h3><label for="inv-email">Their email address</label><input id="inv-email" type="email" placeholder="maria@acme.com" autocomplete="off" maxlength="254"><label for="inv-role">Role</label><select id="inv-role"><option value="member">Member — sees runs and customers, assigns runs</option><option value="viewer">Viewer — can look, can’t change anything</option><option value="owner">Owner — everything, including share links, computers and team</option></select><p><button id="inv-go" type="button" class="btn btn-pri">Create invite link</button></p>'+msgSlot("inv")+revSlot("inv")+'</div>';}el.innerHTML=h;el.querySelectorAll("button[data-rmuser]").forEach(function(btn){btn.onclick=function(){clearMsg();var id=btn.getAttribute("data-rmuser");if(!confirm("Remove "+btn.getAttribute("data-label")+" from this workspace?\n\nThey lose access right away. Runs and share links stay.")){return;}api("/v1/orgs/"+S.org+"/members/"+encodeURIComponent(id),{method:"DELETE"}).then(function(x){if(!x.ok){say("mem-"+id,"err",errHtml("removing that person",x));return;}if(String(btn.getAttribute("data-label")||"").toLowerCase()===String(ME||"").toLowerCase()){location.reload();return;}loadAll();});};});el.querySelectorAll("button[data-rminv]").forEach(function(btn){btn.onclick=function(){clearMsg();var id=btn.getAttribute("data-rminv");if(!confirm("Cancel the invite for "+btn.getAttribute("data-label")+"? The link stops working.")){return;}api("/v1/orgs/"+S.org+"/invites/"+encodeURIComponent(id),{method:"DELETE"}).then(function(x){if(!x.ok){say("inv-"+id,"err",errHtml("cancelling the invite",x));return;}loadAll();});};});var go=byId("inv-go");if(go){go.onclick=function(){clearMsg();var email=byId("inv-email").value.trim();var r=byId("inv-role").value;if(!email||email.indexOf("@")<1){say("inv","err","Type their email address first.");return;}go.disabled=true;api("/v1/orgs/"+S.org+"/invites",{method:"POST",body:{email:email,role:r}}).then(function(x){go.disabled=false;if(!x.ok){say("inv","err",errHtml("creating the invite",x));return;}var url=x.json.url||"";var exp=dayWords(x.json.expires_at);setRev("inv",'<p class="ok-t"><strong>✓ Invite link for '+esc(email)+' ('+esc(roleWords(r))+').</strong></p><p class="small mut">It works once, only for '+esc(email)+', until '+esc(exp)+'. Send it yourself — EPI doesn’t email anyone.</p><label class="small">The link</label>'+copyBox(url,"wrap-anywhere")+'<label class="small">Ready-to-send message</label>'+copyPre(inviteMessage(email,url,exp),"Copy message","msgbox"));loadAll();});};}}
document.getElementById("signout").onclick=function(){fetch("/auth/logout",{method:"POST",credentials:"same-origin"}).then(function(){location.reload();}).catch(function(){location.reload();});};
boot();
`;

app.get("/", async (c) => {
  let email: string | null = null;
  try {
    email = (await userFromRequest(c.env.DB, c.req.raw))?.email ?? null;
  } catch {
    email = null;
  }
  if (!email) {
    return c.html(page("EPI Cloud — sealed evidence for AI runs", landing(!!c.env.GOOGLE_CLIENT_ID)));
  }
  const script = `var TRUST_ORIGIN=${JSON.stringify(TRUST_ORIGIN)};var ME=${scriptJson(email)};\n` + DASH_JS;
  return c.html(page("EPI Cloud — your workspace", DASH_SHELL, { script, user: email, wide: true }));
});

// API paths keep JSON 404s; a person who mistypes a URL gets a small page.
function wantsHtml(path: string, accept: string): boolean {
  if (!accept.includes("text/html")) return false;
  if (path.startsWith("/v1/") || path.startsWith("/w/") || path.startsWith("/.well-known")) return false;
  if (/^\/auth\/device\/[^/]+\/status$/.test(path)) return false;
  return true;
}

app.notFound((c) => {
  if (wantsHtml(new URL(c.req.url).pathname, c.req.header("Accept") ?? "")) {
    return c.html(
      page(
        "Page not found — EPI Cloud",
        `<span class="tag">404</span><h1>We couldn’t find that page</h1>` +
          `<p class="lede">The address may be mistyped, or the page has moved.</p>` +
          `<p><a class="btn btn-pri" href="/">Go to EPI Cloud</a></p>` +
          `<p class="small mut">Looking for a share link? Those open on <a href="https://epilabs.org">epilabs.org</a>.</p>`,
      ),
      404,
    );
  }
  return c.json({ error: { code: "not_found", message: "Unknown route." } }, 404);
});

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
