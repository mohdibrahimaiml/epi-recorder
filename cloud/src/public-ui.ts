// Public (anonymous) pages for cloud.epilabs.org: the dark editorial skin that
// matches epilabs.org, so a visitor arriving from the film sees one brand.
// Signed-in pages stay on the light "paper" app shell in ui.ts.
//
// Constraint kept from ui.ts: no external stylesheets, fonts, images, or
// tracking. Serif/mono fall back to system faces when the brand fonts are not
// installed, so the page makes zero third-party requests.

export const PUBLIC_CSS = [
  ":root{color-scheme:dark;--bg:#000;--fg:#fafafa;--body:#a1a1aa;--mut:#7c7c86;",
  "--line:rgba(255,255,255,.09);--em:#10b981;",
  "--serif:'Instrument Serif',Georgia,'Times New Roman',serif;",
  "--mono:ui-monospace,'JetBrains Mono',Consolas,monospace}",
  "*,*::before,*::after{box-sizing:border-box}",
  "html{-webkit-text-size-adjust:100%}",
  "body{margin:0;background:var(--bg);color:var(--body);",
  "font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif;",
  "line-height:1.6;-webkit-font-smoothing:antialiased;overflow-x:hidden}",
  ".c-grid{position:fixed;inset:0;pointer-events:none;z-index:0;",
  "background-image:repeating-linear-gradient(90deg,transparent 0 63px,rgba(255,255,255,.045) 63px 64px)}",
  ".c-nav{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;",
  "gap:1rem;padding:1.1rem clamp(20px,4vw,64px);border-bottom:1px solid var(--line)}",
  ".c-brand{display:flex;align-items:center;gap:.6rem;color:var(--fg);text-decoration:none;white-space:nowrap;",
  "font-family:var(--mono);font-size:.72rem;letter-spacing:.22em}",
  ".c-dot{width:7px;height:7px;border-radius:50%;background:var(--em);box-shadow:0 0 10px var(--em);flex:0 0 auto}",
  ".c-chip{border:1px solid var(--line);padding:.15rem .45rem;border-radius:3px;color:var(--body);letter-spacing:.12em}",
  ".c-links{display:flex;gap:1.25rem;flex-wrap:wrap;font-family:var(--mono);font-size:.68rem;letter-spacing:.06em}",
  ".c-links a{color:var(--mut);text-decoration:none}",
  ".c-links a:hover{color:var(--fg)}",
  ".c-main{position:relative;z-index:1;max-width:68rem;margin:0 auto;padding:clamp(64px,12vh,140px) clamp(20px,4vw,64px) 5rem}",
  ".c-eyebrow{display:flex;align-items:center;gap:.65rem;font-family:var(--mono);font-size:.7rem;",
  "letter-spacing:.2em;text-transform:uppercase;color:var(--mut)}",
  ".c-h1{font-size:clamp(2.6rem,6.4vw,4.6rem);line-height:1.02;letter-spacing:-.04em;color:var(--fg);",
  "font-weight:400;margin:1.4rem 0 0;max-width:52rem}",
  ".c-h1 em{font-family:var(--serif);font-style:italic;color:var(--em);letter-spacing:-.01em}",
  ".c-lede{margin-top:1.4rem;font-size:clamp(1rem,1.4vw,1.15rem);max-width:38rem;color:var(--body)}",
  ".c-signin{display:flex;gap:.75rem;flex-wrap:wrap;margin-top:2.2rem}",
  ".c-btn{display:inline-flex;align-items:center;gap:.6rem;padding:.85rem 1.4rem;border-radius:4px;",
  "text-decoration:none;font-size:.9rem;font-weight:500;border:1px solid transparent}",
  ".c-btn--primary{background:var(--fg);color:#000}",
  ".c-btn--ghost{border-color:var(--line);color:var(--fg);background:transparent}",
  ".c-btn:hover{opacity:.9}",
  ".c-free{margin-top:1.1rem;font-family:var(--mono);font-size:.7rem;color:var(--mut);letter-spacing:.04em}",
  ".c-steps{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--line);",
  "margin-top:clamp(3rem,8vh,6rem)}",
  ".c-step{padding:1.6rem 1.4rem;border-right:1px solid var(--line)}",
  ".c-step:last-child{border-right:0}",
  ".c-num{font-family:var(--mono);font-size:.68rem;color:var(--em);letter-spacing:.14em}",
  ".c-step h3{color:var(--fg);font-size:1rem;font-weight:500;margin:.7rem 0 .4rem}",
  ".c-step p{margin:0;font-size:.9rem;color:var(--body)}",
  ".c-step code{font-family:var(--mono);font-size:.82em;color:var(--fg);",
  "background:rgba(255,255,255,.06);padding:.1rem .3rem;border-radius:3px}",
  ".c-foot{position:relative;z-index:1;border-top:1px solid var(--line);",
  "padding:1.4rem clamp(20px,4vw,64px);display:flex;justify-content:space-between;",
  "gap:1rem;flex-wrap:wrap;font-family:var(--mono);font-size:.68rem;color:var(--mut);letter-spacing:.06em}",
  ".c-foot a{color:var(--mut)}",
  "@media(max-width:820px){.c-steps{grid-template-columns:1fr}",
  ".c-step{border-right:0;border-bottom:1px solid var(--line)}",
  ".c-step:last-child{border-bottom:0}}",
].join("\n");

/** Anonymous page in the epilabs.org editorial skin. No scripts, no externals. */
export function publicPage(title: string, inner: string): string {
  return (
    `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width,initial-scale=1">` +
    `<meta name="robots" content="noindex,nofollow">` +
    `<meta name="theme-color" content="#000000"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%23000'/%3E%3Ccircle cx='16' cy='16' r='7' fill='%2310b981'/%3E%3C/svg%3E">` +
    `<title>${title}</title><style>${PUBLIC_CSS}</style></head><body>` +
    `<div class="c-grid"></div>` +
    `<header class="c-nav">` +
    `<a class="c-brand" href="/"><span class="c-dot"></span>EPI LABS<span class="c-chip">Cloud</span></a>` +
    `<nav class="c-links">` +
    `<a href="https://epilabs.org">epilabs.org</a>` +
    `<a href="https://epilabs.org/verify/">verify a file</a>` +
    `<a href="https://github.com/mohdibrahimaiml/epi-recorder">GitHub</a>` +
    `<a href="/.well-known/epi-witness-key.json">witness key</a>` +
    `</nav></header>` +
    `<main class="c-main">${inner}</main>` +
    `<footer class="c-foot"><span>Sealed evidence for AI runs · MIT</span>` +
    `<span><a href="https://epilabs.org/plans">Plans</a> · <a href="https://epilabs.org/how-it-works">How EPI works</a></span>` +
    `</footer></body></html>`
  );
}
