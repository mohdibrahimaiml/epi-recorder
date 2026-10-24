// Cloud page shell matching the epilabs.org visual language (site/css/site.css
// light tokens): paper ground, white document cards, hard edges, EPI-green
// accent, serif display + system sans/mono. Fully inline: no external
// fonts, stylesheets, images, or tracking. Anonymous pages stay static
// (no <script>); signed-in pages add small same-origin fetch scripts.

export const SITE_CSS = [
  ":root{color-scheme:dark;--bg:#000;--bg-2:#08090b;--bg-3:#0b0c0e;",
  "--ink:#fafafa;--body:#a1a1aa;--mut:#7c7c86;--dim:#6b6b75;",
  "--edge:rgba(255,255,255,.12);--acc:#10b981;--acc-hi:#34d399;--acc-bg:rgba(16,185,129,.12);",
  "--bad:#f43f5e;--bad-bg:rgba(244,63,94,.12);--warn:#f59e0b;--warn-bg:rgba(245,158,11,.12);",
  "--serif:'Instrument Serif',Georgia,'Times New Roman',serif;",
  "--mono:ui-monospace,'JetBrains Mono',Consolas,monospace;}",
  "*,*::before,*::after{box-sizing:border-box}",
  "html{-webkit-text-size-adjust:100%}",
  "body{font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif;",
  "background:var(--bg);color:var(--body);line-height:1.65;font-size:16px;",
  "margin:0;overflow-x:hidden;-webkit-font-smoothing:antialiased}",
  ".wrap{max-width:44rem;margin:0 auto;padding:1.2rem clamp(16px,4vw,44px) 4rem}",
  ".wide .wrap,.wide .nav-in{max-width:68rem}",
  ".nav{border-bottom:1px solid var(--edge);background:rgba(0,0,0,.86);",
  "backdrop-filter:blur(10px);position:sticky;top:0;z-index:20}",
  ".nav-in{max-width:68rem;margin:0 auto;padding:.8rem clamp(16px,4vw,44px);",
  "display:flex;align-items:center;gap:1rem;flex-wrap:wrap}",
  ".brand{display:flex;align-items:center;gap:.55rem;font-family:var(--mono);",
  "font-size:.72rem;letter-spacing:.2em;color:var(--ink);text-decoration:none;white-space:nowrap}",
  ".bdot{width:7px;height:7px;border-radius:50%;background:var(--acc);box-shadow:0 0 10px var(--acc);flex:0 0 auto}",
  ".chip{border:1px solid var(--edge);padding:.12rem .4rem;border-radius:3px;color:var(--body);letter-spacing:.12em}",
  ".nav-links{margin-left:auto;display:flex;gap:1.1rem;font-family:var(--mono);",
  "font-size:.68rem;letter-spacing:.05em;flex-wrap:wrap}",
  ".nav-links a{color:var(--mut);text-decoration:none}",
  ".nav-links a:hover{color:var(--ink)}",
  ".nav-user{margin-left:auto;display:flex;align-items:center;gap:.7rem;font-size:.78rem;",
  "color:var(--mut);flex-wrap:wrap;min-width:0}",
  ".nav-user .who{overflow-wrap:anywhere}",
  ".nav-user a{color:var(--mut)}",
  ".linkbtn{background:none;border:0;padding:0;color:var(--mut);text-decoration:underline;cursor:pointer;font-size:inherit}",
  "h1,h2{font-family:Inter,system-ui,sans-serif;color:var(--ink);letter-spacing:-.03em;",
  "line-height:1.1;font-weight:400}",
  "h1{font-size:clamp(1.8rem,4vw,2.6rem);margin:1.2rem 0 .6rem}",
  "h2{font-size:clamp(1.25rem,2.4vw,1.55rem);margin:1.2rem 0 .4rem}",
  ".tag{display:inline-flex;align-items:center;gap:10px;font-family:var(--mono);",
  "font-size:.66rem;letter-spacing:.18em;text-transform:uppercase;color:var(--mut)}",
  ".tag::before{content:'';width:8px;height:8px;border-radius:50%;background:var(--acc);box-shadow:0 0 8px var(--acc)}",
  ".lede{color:var(--body)}",
  ".card{background:var(--bg-3);border:1px solid var(--edge);border-radius:6px;",
  "padding:1.15rem 1.2rem;margin:1rem 0;max-width:100%}",
  ".btn{display:inline-block;background:var(--ink);color:#000;padding:.62rem 1.2rem;",
  "border-radius:4px;text-decoration:none;border:1px solid var(--ink);font:inherit;font-weight:500;cursor:pointer}",
  ".btn-pri{background:var(--ink);border-color:var(--ink);color:#000}",
  ".btn-sec{background:transparent;color:var(--ink);border:1px solid var(--edge)}",
  ".btn-sm{padding:.3rem .7rem;font-size:.82rem}",
  "button{font:inherit;padding:.5rem 1.1rem;cursor:pointer;max-width:100%}",
  "button:disabled{opacity:.55;cursor:progress}",
  "input,select,textarea{font:inherit;padding:.5rem .65rem;width:100%;max-width:100%;",
  "box-sizing:border-box;margin:.35rem 0;border:1px solid var(--edge);border-radius:4px;",
  "background:#060708;color:var(--ink)}",
  "input:focus,select:focus,textarea:focus,a:focus-visible,button:focus-visible{",
  "outline:2px solid var(--acc);outline-offset:2px}",
  "code,.val{font-family:var(--mono);font-size:.85em;background:rgba(255,255,255,.06);",
  "padding:.1rem .3rem;border-radius:3px;word-break:break-all;overflow-wrap:anywhere;color:var(--ink)}",
  ".wrap-anywhere,.out{word-break:break-all;overflow-wrap:anywhere;max-width:100%;display:block}",
  ".mut{color:var(--mut)}.small{font-size:.85rem}",
  "#msg,.msg{min-height:1.4em}",
  ".err{background:var(--bad-bg);border:1px solid rgba(244,63,94,.5);padding:.7rem .9rem;",
  "border-radius:4px;max-width:100%;color:#fda4af}",
  ".ok{background:var(--acc-bg);border:1px solid rgba(16,185,129,.5);padding:.7rem .9rem;",
  "border-radius:4px;max-width:100%;color:#6ee7b7}",
  ".warn{background:var(--warn-bg);border:1px solid rgba(245,158,11,.5);padding:.7rem .9rem;",
  "border-radius:4px;max-width:100%;color:#fcd34d}",
  "ol.setup>li{margin:.9rem 0}",
  ".step{border-left:2px solid var(--edge);padding:.2rem 0 .2rem 1rem;margin:.8rem 0;max-width:100%}",
  ".step.done{border-color:var(--acc)}",
  ".step.current{border-color:var(--ink)}",
  ".step.locked{opacity:.55}",
  ".stephead{display:flex;align-items:baseline;gap:.6rem;flex-wrap:wrap}",
  ".stepnum{font-family:var(--mono);font-size:.72rem;color:var(--mut)}",
  ".mark{font-weight:700}",
  ".mark.done{color:var(--acc-hi)}",
  ".tabs{display:flex;gap:.4rem;flex-wrap:wrap;margin:1rem 0}",
  ".tab{border:1px solid var(--edge);background:transparent;border-radius:4px;",
  "padding:.45rem .9rem;color:var(--mut);font-size:.85rem}",
  ".tab.active{background:var(--ink);color:#000;border-color:var(--ink)}",
  ".twrap{overflow-x:auto;max-width:100%}",
  "table.tbl{border-collapse:collapse;width:100%;font-size:.85rem}",
  "table.tbl th,table.tbl td{text-align:left;padding:.55rem .6rem;",
  "border-bottom:1px solid rgba(255,255,255,.07);vertical-align:top}",
  "table.tbl th{font-family:var(--mono);font-size:.66rem;letter-spacing:.08em;",
  "text-transform:uppercase;color:var(--mut);font-weight:500}",
  "table.tbl tr:hover td{background:rgba(255,255,255,.02)}",
  ".pill{display:inline-block;padding:.1rem .5rem;border-radius:999px;font-size:.72rem;",
  "border:1px solid var(--edge);white-space:nowrap;color:var(--body)}",
  ".pill.ok{background:var(--acc-bg);border-color:rgba(16,185,129,.5);color:#6ee7b7}",
  ".pill.bad{background:var(--bad-bg);border-color:rgba(244,63,94,.5);color:#fda4af}",
  ".pill.warn{background:var(--warn-bg);border-color:rgba(245,158,11,.5);color:#fcd34d}",
  "details.adv{margin-top:1rem}",
  "details.adv summary{cursor:pointer;color:var(--mut)}",
  ".copyrow{display:flex;gap:.5rem;align-items:flex-start;flex-wrap:wrap}",
  ".copyrow code{flex:1;min-width:0}",
  "pre.cmd{background:#050607;color:#e6edf3;border:1px solid var(--edge);padding:.8rem 1rem;",
  "border-radius:4px;overflow-x:auto;max-width:100%;font-size:.82rem;",
  "white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}",
  "pre.cmd .c{color:#8b949e}",
  "a{color:var(--acc-hi)}",
  "h3{color:var(--ink);font-size:1rem;margin:1.2rem 0 .4rem;font-weight:500}",
  "label.inline{display:inline-flex;align-items:center;gap:.4rem;margin-right:1rem}",
  "label.inline input{width:auto;margin:0}",
  ".note{padding:.6rem .8rem;margin:.6rem 0;font-size:.9rem;border:1px solid var(--edge);",
  "background:var(--bg-2);border-radius:4px}",
  ".note.err{background:var(--bad-bg);border-color:rgba(244,63,94,.5)}",
  ".note.ok{background:var(--acc-bg);border-color:rgba(16,185,129,.5)}",
  ".ok-t{color:var(--acc-hi)}",
  ".reveal{border:1px solid rgba(16,185,129,.5);background:var(--bg-3);padding:.9rem 1rem;",
  "margin:.8rem 0;border-radius:6px}",
  ".reveal p{margin:.4rem 0}.reveal label{display:block;margin-top:.6rem}",
  ".revdone{margin-top:.8rem!important}",
  ".copyblock{display:flex;flex-direction:column;align-items:flex-start;gap:.35rem;margin:.4rem 0 .6rem}",
  ".copyblock pre.cmd{margin:0;width:100%}",
  ".acts{display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.4rem;align-items:center}",
  ".acts select{width:auto;min-width:8rem;margin:0}",
  ".wshead{display:flex;justify-content:space-between;align-items:flex-end;gap:1rem;",
  "flex-wrap:wrap;margin-top:1.4rem}",
  ".wsname{margin:.3rem 0 0;font-family:var(--serif);font-style:italic;font-size:clamp(1.8rem,4vw,2.4rem)}",
  ".wspick select{width:auto;min-width:12rem}",
  ".planbar{display:flex;flex-wrap:wrap;gap:.2rem 1rem;align-items:baseline;",
  "border:1px solid var(--edge);background:var(--bg-3);padding:.55rem .8rem;",
  "margin:.9rem 0;border-radius:4px;font-size:.85rem}",
  ".planbar .upg{margin-left:auto;font-weight:600}",
  ".planbar .full{color:var(--warn);font-weight:600}",
  "tr.sub td{padding:0 .6rem;border-bottom:0}",
  "tr.sub td:empty{display:none}",
  ".hero{margin-top:1.6rem}",
  ".card h3,.card h2{margin-top:0}",
  "pre.msgbox{background:var(--bg-2);color:var(--ink);border:1px solid var(--edge);",
  "padding:.8rem 1rem;margin:0;width:100%;white-space:pre-wrap;overflow-wrap:anywhere;",
  "font:inherit;font-size:.9rem;border-radius:4px}",
  ".hero h1{font-size:clamp(1.8rem,5vw,2.6rem);margin:.6rem 0}",
  ".how{counter-reset:how;list-style:none;padding:0;margin:1rem 0;display:grid;gap:.8rem}",
  ".how li{counter-increment:how;background:var(--bg-3);border:1px solid var(--edge);",
  "padding:.8rem 1rem .8rem 3.2rem;position:relative;border-radius:6px}",
  ".how li::before{content:counter(how);position:absolute;left:1rem;top:.75rem;",
  "width:1.5rem;height:1.5rem;border-radius:50%;background:var(--acc);color:#00170e;",
  "font-weight:700;font-size:.85rem;display:flex;align-items:center;justify-content:center}",
  ".signin{display:flex;gap:.6rem;flex-wrap:wrap;margin:1.2rem 0}",
  "@media (max-width:600px){",
  "table.tbl thead{display:none}",
  "table.tbl,table.tbl tbody,table.tbl tr,table.tbl td{display:block;width:100%}",
  "table.tbl tr{border:1px solid var(--edge);background:var(--bg-3);margin:.6rem 0;",
  "padding:.3rem .7rem;border-radius:6px}",
  "table.tbl tr.sub{border:0;background:none;margin:-.5rem 0 .6rem;padding:0}",
  "table.tbl tr.empty{padding:.6rem .7rem}",
  "table.tbl td{border:0;padding:.3rem 0}",
  "table.tbl td[data-l]:not([data-l=''])::before{content:attr(data-l);display:block;",
  "font-family:var(--mono);font-size:.64rem;letter-spacing:.08em;text-transform:uppercase;color:var(--mut)}",
  ".planbar .upg{margin-left:0}",
  "}",
].join("\n");

export function esc(s: string): string {
  return s.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]!);
}

function nav(user?: string): string {
  if (user !== undefined) {
    // Signed-in chrome: who you are + sign out, small, top right.
    return (
      `<nav class="nav"><div class="nav-in">` +
      `<a class="brand" href="/"><span class="bdot"></span>EPI LABS<span class="chip">Cloud</span></a>` +
      `<span class="nav-user"><a href="https://epilabs.org/how-it-works">Help</a>` +
      `<span class="who">Signed in as <strong>${esc(user)}</strong></span>` +
      `<button type="button" class="linkbtn" id="signout">Sign out</button></span>` +
      `</div></nav>`
    );
  }
  return (
    `<nav class="nav"><div class="nav-in">` +
    `<a class="brand" href="/"><span class="bdot"></span>EPI LABS<span class="chip">Cloud</span></a>` +
    `<span class="nav-links"><a href="https://epilabs.org">epilabs.org</a>` +
    `<a href="https://epilabs.org/verify/">verify a file</a>` +
    `<a href="https://github.com/mohdibrahimaiml/epi-recorder">GitHub</a>` +
    `<a href="/.well-known/epi-witness-key.json">witness key</a></span>` +
    `</div></nav>`
  );
}

/** Full page in the epilabs.org visual language. No external assets. */
export function page(title: string, inner: string, opts: { script?: string; user?: string; wide?: boolean } = {}): string {
  return (
    `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width,initial-scale=1">` +
    `<meta name="robots" content="noindex,nofollow">` +
    `<meta name="theme-color" content="#F6F8FA" media="(prefers-color-scheme: light)">` +
    `<meta name="theme-color" content="#0D1117" media="(prefers-color-scheme: dark)">` +
    `<title>${esc(title)}</title><style>${SITE_CSS}</style></head>` +
    `<body${opts.wide ? ` class="wide"` : ``}>${nav(opts.user)}<div class="wrap">${inner}</div>` +
    (opts.script ? `<script>${opts.script}</script>` : ``) +
    `</body></html>`
  );
}
