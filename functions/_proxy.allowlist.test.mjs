// WP-SEC-2: CORS allowlist for the Cloudflare Pages Functions proxy.
//
// The proxy (functions/_proxy.js) forwards /api/*, /scitt/* and
// /.well-known/* to the Render backend with credentials. The old check
//   origin.endsWith("epilabs.org") || origin.includes("pages.dev")
// also matched https://evilepilabs.org and ANY *.pages.dev project
// (proven live: evilepilabs.org received ACAO + credentials).
//
// This test loads the SHIPPED functions/_proxy.js source, extracts its pure
// allowlist logic plus the preflight handler, and asserts the behavior.
// Run: node --test functions/
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "_proxy.js"),
  "utf8",
);

function extractFunction(src, name) {
  const start = src.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `function ${name} not found in _proxy.js`);
  let depth = 0;
  let i = src.indexOf("{", start);
  for (; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) return src.slice(start, i + 1);
    }
  }
  throw new Error(`unbalanced braces in ${name}`);
}

// Pure section: ALLOWED set + PREVIEW regex + allowedOrigin(). No DOM use.
const allowlistSrc =
  SRC.slice(SRC.indexOf("const ALLOWED"), SRC.indexOf("const BACKEND")) +
  extractFunction(SRC, "allowedOrigin");
// Preflight handler needs the Fetch API globals inside the sandbox.
const preflightSrc = extractFunction(SRC, "corsPreflight").replace(
  "function corsPreflight",
  "function __corsPreflight",
);

function loadAllowlist() {
  const sandbox = {};
  vm.createContext(sandbox);
  vm.runInContext(`${allowlistSrc}; this.__allowedOrigin = allowedOrigin;`, sandbox);
  return sandbox.__allowedOrigin;
}

function loadPreflight() {
  const sandbox = { Response, Headers };
  vm.createContext(sandbox);
  vm.runInContext(
    `${allowlistSrc}\n${preflightSrc}\nthis.__preflight = __corsPreflight;`,
    sandbox,
  );
  return sandbox.__preflight;
}

const ctxWithOrigin = (origin) => ({
  request: { headers: { get: (k) => (String(k).toLowerCase() === "origin" ? origin : null) } },
});

describe("allowedOrigin", () => {
  const allowedOrigin = loadAllowlist();

  it("allows the exact production origins", () => {
    assert.equal(allowedOrigin("https://epilabs.org"), "https://epilabs.org");
    assert.equal(allowedOrigin("https://www.epilabs.org"), "https://www.epilabs.org");
  });

  it("allows this project's Pages previews", () => {
    assert.equal(
      allowedOrigin("https://wp-sec-2-cors.epi-recorder.pages.dev"),
      "https://wp-sec-2-cors.epi-recorder.pages.dev",
    );
  });

  it("rejects lookalike and foreign origins", () => {
    for (const evil of [
      "https://evilepilabs.org", // the live bug: endsWith("epilabs.org")
      "https://epilabs.org.evil.com",
      "https://notepilabs.org",
      "https://evil.pages.dev", // any *.pages.dev was allowed before
      "https://epi-recorder.pages.dev.evil.com",
      "https://epi-recorder.evil-pages.dev",
      "http://epilabs.org", // exact https only
      "https://epilabs.org:443.evil.com",
      "https://epilabs.org\n", // header-injection probe ($-anchor bypass)
      "https://x.epi-recorder.pages.dev\r\n",
      "",
      null,
      undefined,
    ]) {
      assert.equal(allowedOrigin(evil), null, `must reject ${String(evil)}`);
    }
  });
});

describe("corsPreflight", () => {
  const preflight = loadPreflight();

  it("reflects ACAO only for allowed origins", () => {
    const good = preflight(ctxWithOrigin("https://epilabs.org"));
    assert.equal(good.headers.get("access-control-allow-origin"), "https://epilabs.org");
    assert.equal(good.headers.get("access-control-allow-credentials"), "true");
    assert.match(good.headers.get("vary") || "", /Origin/);

    const preview = preflight(ctxWithOrigin("https://fix-1.epi-recorder.pages.dev"));
    assert.equal(
      preview.headers.get("access-control-allow-origin"),
      "https://fix-1.epi-recorder.pages.dev",
    );
  });

  it("emits no ACAO for disallowed origins", () => {
    for (const evil of ["https://evilepilabs.org", "https://evil.pages.dev", null]) {
      const res = preflight(ctxWithOrigin(evil));
      assert.equal(res.headers.get("access-control-allow-origin"), null);
      assert.equal(res.headers.get("access-control-allow-credentials"), null);
    }
  });
});

describe("no regression to substring matching", () => {
  // Strip comments: prose may name the old patterns, code must not contain them.
  const code = SRC.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*/g, "");

  it("source contains no endsWith/includes origin checks", () => {
    assert.doesNotMatch(code, /endsWith\(\s*["']epilabs\.org["']\s*\)/);
    assert.doesNotMatch(code, /includes\(\s*["']pages\.dev["']\s*\)/);
  });

  it("both response paths gate on allowedOrigin()", () => {
    const uses = code.match(/allowedOrigin\(/g) || [];
    assert.ok(uses.length >= 2, "proxyToRender and corsPreflight must both call allowedOrigin()");
  });
});
