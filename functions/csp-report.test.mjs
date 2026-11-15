import assert from "node:assert/strict";
import { describe, it } from "node:test";
import vm from "node:vm";

import fs from "node:fs";

const SRC = fs.readFileSync(new URL("./csp-report.js", import.meta.url), "utf8");

function load() {
  const body = SRC.replace("export async function onRequest", "async function __onRequest");
  const sandbox = { Response, JSON, Number, String, Array, console };
  vm.createContext(sandbox);
  vm.runInContext(`${body}\nthis.__run = (ctx) => __onRequest(ctx);`, sandbox);
  return sandbox.__run;
}

function ctx({ method = "POST", body = "", declared = null } = {}) {
  const headers = new Map();
  if (declared !== null) headers.set("content-length", String(declared));
  return {
    request: {
      method,
      headers: { get: (k) => headers.get(k.toLowerCase()) ?? null },
      text: async () => body,
    },
  };
}

describe("csp-report", () => {
  it("rejects anything but POST", async () => {
    const run = load();
    const res = await run(ctx({ method: "GET" }));
    assert.equal(res.status, 405);
  });

  it("accepts a legacy report-uri body and logs a summary", async () => {
    const run = load();
    const logged = [];
    const original = console.log;
    console.log = (line) => logged.push(line);
    try {
      const res = await run(
        ctx({
          body: JSON.stringify({
            "csp-report": {
              "violated-directive": "script-src",
              "blocked-uri": "https://evil.example/x.js",
              "document-uri": "https://epilabs.org/verify?token=secret#k=abc",
            },
          }),
        }),
      );
      assert.equal(res.status, 204);
    } finally {
      console.log = original;
    }
    assert.equal(logged.length, 1);
    const parsed = JSON.parse(logged[0]);
    assert.equal(parsed.directive, "script-src");
    // The token must never reach the log.
    assert.ok(!logged[0].includes("secret"), "query string leaked into the log");
    assert.ok(!logged[0].includes("#k="), "fragment leaked into the log");
  });

  it("accepts the Reporting API array shape", async () => {
    const run = load();
    const logged = [];
    const original = console.log;
    console.log = (line) => logged.push(line);
    try {
      const res = await run(
        ctx({
          body: JSON.stringify([
            { type: "csp-violation", body: { "effective-directive": "connect-src" } },
          ]),
        }),
      );
      assert.equal(res.status, 204);
    } finally {
      console.log = original;
    }
    assert.ok(logged[0].includes("connect-src"));
  });

  it("never reads an oversized body", async () => {
    const run = load();
    let read = false;
    const res = await run({
      request: {
        method: "POST",
        headers: { get: (k) => (k.toLowerCase() === "content-length" ? "999999" : null) },
        text: async () => {
          read = true;
          return "";
        },
      },
    });
    assert.equal(res.status, 204);
    assert.equal(read, false, "oversized body must not be read");
  });

  it("survives a malformed body", async () => {
    const run = load();
    const res = await run(ctx({ body: "not json at all" }));
    assert.equal(res.status, 204);
  });
});
