// C7: the three /.well-known names with no caller answer 410, not a proxy to
// the retiring Render portal. Everything else keeps forwarding.
//
// Loads the SHIPPED function source (like _proxy.allowlist.test.mjs) so the
// test covers what ships, not a copy.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const SRC = readFileSync(
  new URL("./.well-known/[[path]].js", import.meta.url),
  "utf8",
);

function load() {
  let proxied = 0;
  const sandbox = {
    Response,
    Headers,
    URL,
    corsPreflight: () => new Response(null, { status: 204 }),
    proxyToRender: async () => {
      proxied += 1;
      return new Response("proxied", { status: 200 });
    },
  };
  vm.createContext(sandbox);
  const body =
    SRC.replace(/^import .*$/m, "")
      .replace("export async function onRequest", "async function onRequest") +
    "\nthis.__run = onRequest;";
  vm.runInContext(body, sandbox);
  return { run: sandbox.__run, proxied: () => proxied };
}

function ctx(name, staticStatus = 404) {
  return {
    request: {
      method: "GET",
      url: `https://epilabs.org/.well-known/${name}`,
      headers: new Headers(),
    },
    next: async () =>
      staticStatus === 200
        ? new Response("static", { status: 200 })
        : new Response("missing", { status: staticStatus }),
  };
}

for (const name of ["webfinger", "apple-app-site-association", "assetlinks.json"]) {
  test(`${name} answers 410 and does not wake the portal`, async () => {
    const { run, proxied } = load();
    const res = await run(ctx(name));
    assert.equal(res.status, 410);
    assert.equal(res.headers.get("content-type"), "application/json");
    const body = await res.json();
    assert.equal(body.error.code, "gone");
    assert.match(body.error.message, /cloud\.epilabs\.org/);
    assert.equal(proxied(), 0);
  });
}

test("a committed static file still wins over the retired list", async () => {
  const { run, proxied } = load();
  const res = await run(ctx("webfinger", 200));
  assert.equal(res.status, 200);
  assert.equal(await res.text(), "static");
  assert.equal(proxied(), 0);
});

test("oauth metadata still proxies", async () => {
  const { run, proxied } = load();
  const res = await run(ctx("oauth-authorization-server"));
  assert.equal(res.status, 200);
  assert.equal(await res.text(), "proxied");
  assert.equal(proxied(), 1);
});

test("an unknown name is still a plain 404", async () => {
  const { run, proxied } = load();
  const res = await run(ctx("something-else"));
  assert.equal(res.status, 404);
  assert.equal(proxied(), 0);
});
