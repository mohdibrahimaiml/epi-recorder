// Cloud page shell matching the epilabs.org visual language (site/css/site.css
// light tokens): paper ground, white document cards, hard edges, EPI-green
// accent, serif display + system sans/mono. Fully inline: no external
// fonts, stylesheets, images, or tracking. Anonymous pages stay static
// (no <script>); signed-in pages add small same-origin fetch scripts.

export const SITE_CSS = [
  ":root{color-scheme:light;--bg:#F6F8FA;--bg-2:#EEF1F4;--bg-3:#FFFFFF;",
  "--ink:#0D1117;--body:#24292F;--mut:#57606A;--dim:#66707C;",
  "--edge:#D0D7DE;--acc:#1A7F37;--acc-hi:#116329;--acc-bg:#DAFBE1;",
  "--bad:#CF222E;--bad-bg:#FFEBE9;--warn:#9A6700;--warn-bg:#FFF8C5;",
  "--shadow:4px 4px 0 rgba(13,17,23,.07);}",
  "*,*::before,*::after{box-sizing:border-box}",
  "html{-webkit-text-size-adjust:100%}",
  "body{font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif;",
  "background:var(--bg);color:var(--body);line-height:1.68;font-size:16px;",
  "margin:0;overflow-x:hidden}",
  "body::before{content:'';display:block;height:3px;background:var(--acc)}",
  ".wrap{max-width:40rem;margin:0 auto;padding:0 clamp(20px,4vw,44px) 4rem}",
  ".nav{border-bottom:1px solid var(--edge);background:var(--bg-3)}",
  ".nav-in{max-width:40rem;margin:0 auto;padding:.8rem clamp(20px,4vw,44px);",
  "display:flex;align-items:center;gap:1rem;flex-wrap:wrap}",
  ".brand{font-family:Fraunces,Georgia,'Times New Roman',serif;font-weight:700;",
  "color:var(--ink);letter-spacing:-.02em;text-decoration:none;font-size:1.1rem}",
  ".brand em{font-style:normal;color:var(--acc)}",
  ".nav-links{margin-left:auto;display:flex;gap:1rem;font-size:.85rem;flex-wrap:wrap}",
  ".nav-links a{color:var(--mut);text-decoration:none}",
  "h1,h2{font-family:Fraunces,Georgia,'Times New Roman',serif;color:var(--ink);",
  "letter-spacing:-.02em;line-height:1.14;font-weight:500}",
  ".tag{display:inline-flex;align-items:center;gap:10px;",
  "font-family:ui-monospace,'JetBrains Mono',Consolas,monospace;font-size:.68rem;",
  "font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:var(--ink)}",
  ".tag::before{content:'';width:10px;height:10px;background:var(--acc)}",
  ".lede{color:var(--mut)}",
  ".card{background:var(--bg-3);border:1px solid var(--edge);box-shadow:var(--shadow);",
  "padding:1.2rem 1.2rem;margin:1rem 0;max-width:100%}",
  ".btn{display:inline-block;background:var(--ink);color:#fff;padding:.6rem 1.2rem;",
  "border-radius:.4rem;text-decoration:none;border:1px solid var(--ink);font:inherit;cursor:pointer}",
  ".btn-pri{background:var(--acc);border-color:var(--acc)}",
  ".btn-sec{background:var(--bg-3);color:var(--ink);border:1px solid var(--edge)}",
  "button{font:inherit;padding:.5rem 1.1rem;cursor:pointer;max-width:100%}",
  "input,select{font:inherit;padding:.45rem .6rem;width:100%;max-width:100%;",
  "box-sizing:border-box;margin:.35rem 0;border:1px solid var(--edge);border-radius:.35rem;",
  "background:#fff;color:var(--ink)}",
  "code,.val{font-family:ui-monospace,'JetBrains Mono',Consolas,monospace;font-size:.85em;",
  "background:#f0f0f0;padding:.1rem .3rem;word-break:break-all;overflow-wrap:anywhere}",
  ".wrap-anywhere,.out{word-break:break-all;overflow-wrap:anywhere;max-width:100%;display:block}",
  ".mut{color:var(--mut)}.small{font-size:.85rem}",
  "#msg,.msg{min-height:1.4em}",
  ".err{background:var(--bad-bg);border:1px solid var(--bad);padding:.7rem .9rem;max-width:100%}",
  ".ok{background:var(--acc-bg);border:1px solid var(--acc);padding:.7rem .9rem;max-width:100%}",
  ".warn{background:var(--warn-bg);border:1px solid var(--warn);padding:.7rem .9rem;max-width:100%}",
  "ol.setup>li{margin:.9rem 0}",
  ".step{border-left:3px solid var(--edge);padding:.2rem 0 .2rem 1rem;margin:.8rem 0;max-width:100%}",
  ".step.done{border-color:var(--acc)}",
  ".step.current{border-color:var(--ink)}",
  ".step.locked{opacity:.55}",
  ".stephead{display:flex;align-items:baseline;gap:.6rem;flex-wrap:wrap}",
  ".stepnum{font-family:ui-monospace,Consolas,monospace;font-size:.75rem;color:var(--mut)}",
  ".mark{font-weight:700}",
  ".mark.done{color:var(--acc)}",
  ".tabs{display:flex;gap:.4rem;flex-wrap:wrap;margin:1rem 0}",
  ".tab{border:1px solid var(--edge);background:var(--bg-3);border-radius:.4rem;padding:.45rem .9rem}",
  ".tab.active{background:var(--ink);color:#fff;border-color:var(--ink)}",
  ".twrap{overflow-x:auto;max-width:100%}",
  "table.tbl{border-collapse:collapse;width:100%;font-size:.85rem}",
  "table.tbl th,table.tbl td{text-align:left;padding:.45rem .6rem;border-bottom:1px solid var(--edge);vertical-align:top}",
  "table.tbl th{font-family:ui-monospace,Consolas,monospace;font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;color:var(--mut)}",
  ".pill{display:inline-block;padding:.1rem .5rem;border-radius:1rem;font-size:.75rem;border:1px solid var(--edge);white-space:nowrap}",
  ".pill.ok{background:var(--acc-bg);border-color:var(--acc)}",
  ".pill.bad{background:var(--bad-bg);border-color:var(--bad)}",
  "details.adv{margin-top:1rem}",
  "details.adv summary{cursor:pointer;color:var(--mut)}",
  ".copyrow{display:flex;gap:.5rem;align-items:flex-start;flex-wrap:wrap}",
  ".copyrow code{flex:1;min-width:0}",
  "pre.cmd{background:#0D1117;color:#E6EDF3;padding:.8rem 1rem;border-radius:.4rem;overflow-x:auto;max-width:100%;font-size:.82rem}",
  "pre.cmd .c{color:#8B949E}",
].join("\n");

export function esc(s: string): string {
  return s.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]!);
}

function nav(): string {
  return (
    `<nav class="nav"><div class="nav-in">` +
    `<a class="brand" href="/">EPI<em>.</em>Cloud</a>` +
    `<span class="nav-links"><a href="https://epilabs.org">epilabs.org</a>` +
    `<a href="https://epilabs.org/verify/">verify a file</a>` +
    `<a href="https://github.com/mohdibrahimaiml/epi-recorder">GitHub</a>` +
    `<a href="/.well-known/epi-witness-key.json">witness key</a></span>` +
    `</div></nav>`
  );
}

/** Full page in the epilabs.org visual language. No external assets. */
export function page(title: string, inner: string, opts: { script?: string } = {}): string {
  return (
    `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width,initial-scale=1">` +
    `<meta name="robots" content="noindex,nofollow">` +
    `<meta name="theme-color" content="#F6F8FA">` +
    `<title>${esc(title)}</title><style>${SITE_CSS}</style></head>` +
    `<body>${nav()}<div class="wrap">${inner}</div>` +
    (opts.script ? `<script>${opts.script}</script>` : ``) +
    `</body></html>`
  );
}
