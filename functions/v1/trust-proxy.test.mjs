// Trust-page proxy allow-list + header hygiene.
// Loads the SHIPPED functions/v1/[[path]].js source, extracts its pure
// functions (no Pages runtime needed), and asserts the contract:
// only reviewer endpoints, only GET/POST, token header only, no cookies,
// no-store everywhere, and no backend details on 502.
// Run: node --test functions/v1/
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "[[path]].js"),
  "utf8",
);

function extractFunction(src, name) {
  const start = src.indexOf(`function ${name}(`);
  if (start === -1) {
    const asyncStart = src.indexOf(`async function ${name}(`);
    assert.notEqual(asyncStart, -1, `function ${name} not found`);
    return extractFrom(src, asyncStart);
  }
  return extractFrom(src, start);
}

function extractFrom(src, start) {
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

const allowSrc = extractFunction(SRC, "trustProxyAllowed");
const routesSrc = SRC.slice(SRC.indexOf("const ROUTES"), SRC.indexOf("];", SRC.indexOf("const ROUTES")) + 2);
const proxySrc = extractFunction(SRC, "proxyTrustToCloud").replace(
  "function proxyTrustToCloud",
  "async function __proxyTrustToCloud",
);

function load() {
  const sandbox = { URL, Headers, Request, Response, console };
  vm.createContext(sandbox);
  vm.runInContext(
    `${routesSrc}\n${allowSrc}\n${proxySrc}\nthis.__allowed = trustProxyAllowed;\nthis.__proxy = __proxyTrustToCloud;`,
    sandbox,
  );
  return { allowed: sandbox.__allowed, proxy: sandbox.__proxy };
}

const { allowed, proxy } = load();

describe("trust proxy allow-list", () => {
  it("allows exactly the reviewer endpoints", () => {
    assert.equal(allowed("GET", "/v1/trust/sh_abc123"), true);
    assert.equal(allowed("GET", "/v1/trust/sh_abc123/witness-lines"), true);
    assert.equal(allowed("POST", "/v1/trust/sh_abc123/events"), true);
    assert.equal(allowed("GET", "/v1/orgs/o1/artifacts/art_1/content"), true);
  });

  it("rejects everything else", () => {
    assert.equal(allowed("GET", "/v1/trust"), false);
    assert.equal(allowed("GET", "/v1/trust/"), false);
    assert.equal(allowed("GET", "/v1/orgs/o1/artifacts"), false);
    assert.equal(allowed("GET", "/v1/orgs/o1/artifacts/art_1"), false);
    assert.equal(allowed("POST", "/v1/orgs/o1/artifacts/art_1/content"), false);
    assert.equal(allowed("GET", "/v1/orgs/o1/artifacts/../x/content"), false);
    assert.equal(allowed("GET", "/v1/trust/sh_abc/../../etc"), false);
    assert.equal(allowed("GET", "/v1/trust/sh_abc.evil"), false);
    assert.equal(allowed("PUT", "/v1/trust/sh_abc"), false);
    assert.equal(allowed("DELETE", "/v1/trust/sh_abc"), false);
    assert.equal(allowed("POST", "/v1/trust/sh_abc"), false);
    assert.equal(allowed("GET", "/v1/trust/sh_abc/other"), false);
    assert.equal(allowed("POST", "/v1/trust/sh_abc/witness-lines"), false);
  });

  it("returns 404 JSON with no-store for disallowed paths", async () => {
    const res = await proxy(
      new Request("https://epilabs.org/v1/orgs/o1/artifacts", { headers: { Cookie: "a=b" } }),
      async () => new Response("unreachable", { status: 200 }),
      "https://cloud.example",
    );
    assert.equal(res.status, 404);
    assert.equal(res.headers.get("cache-control"), "no-store");
    assert.match(await res.text(), /not_found/);
  });
});

describe("trust proxy header hygiene", () => {
  async function capturedFetch(input, init) {
    capturedFetch.last = { input, init };
    return new Response('{"ok":true}', {
      status: 200,
      headers: { "set-cookie": "sess=x", "content-type": "application/json" },
    });
  }

  it("forwards only the share token (never cookies or auth)", async () => {
    const req = new Request("https://epilabs.org/v1/trust/sh_1", {
      headers: {
        "X-EPI-Share-Token": "tok123",
        Cookie: "epi_session=deadbeef",
        Authorization: "Bearer nope",
      },
    });
    const res = await proxy(req, capturedFetch, "https://cloud.example");
    assert.equal(res.status, 200);
    const sent = capturedFetch.last.init.headers;
    assert.equal(sent.get("X-EPI-Share-Token"), "tok123");
    assert.equal(sent.get("cookie"), null);
    assert.equal(sent.get("authorization"), null);
    assert.ok(String(capturedFetch.last.input).startsWith("https://cloud.example/v1/trust/sh_1"));
    assert.equal(res.headers.get("set-cookie"), null);
    assert.equal(res.headers.get("cache-control"), "no-store");
  });

  it("forwards content-type on POST events, drops query strings", async () => {
    const req = new Request("https://epilabs.org/v1/trust/sh_1/events?x=1", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-EPI-Share-Token": "t" },
      body: '{"kind":"opened"}',
    });
    const res = await proxy(req, capturedFetch, "https://cloud.example");
    assert.equal(res.status, 200);
    assert.equal(capturedFetch.last.init.headers.get("content-type"), "application/json");
    assert.ok(!String(capturedFetch.last.input).includes("?"));
  });

  it("returns 502 without backend details when the Worker is down", async () => {
    const res = await proxy(
      new Request("https://epilabs.org/v1/trust/sh_1"),
      async () => {
        throw new Error("boom");
      },
      "https://cloud.example",
    );
    assert.equal(res.status, 502);
    const body = await res.text();
    assert.match(body, /bad_gateway/);
    assert.ok(!body.includes("cloud.example"));
    assert.ok(!body.includes("boom"));
  });
});
