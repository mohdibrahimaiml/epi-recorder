/* Verify a .epi with the browser verifier (website/js/epi-verify-core.js) under Node.
 *
 * Usage: node verify_epi_node.mjs <file.epi>
 * Prints a JSON object: {structure, manifest, integrity, signature, trust_level,
 * mismatches, message}. Exit code 0 on success, non-zero on loader failure.
 */
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(here, "..", "..");
const WEB = path.join(REPO, "website");

const sandbox = {
  console,
  crypto: globalThis.crypto,
  fetch: async () => {
    throw new Error("no fetch in verifier test");
  },
  atob: (s) => Buffer.from(s, "base64").toString("binary"),
  btoa: (s) => Buffer.from(s, "binary").toString("base64"),
  setTimeout,
  TextEncoder,
  TextDecoder,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

vm.runInContext(fs.readFileSync(path.join(WEB, "js", "jszip.min.js"), "utf8"), sandbox);
vm.runInContext(fs.readFileSync(path.join(WEB, "js", "epi-verify-core.js"), "utf8"), sandbox);

const target = process.argv[2];
if (!target) {
  console.error("usage: node verify_epi_node.mjs <file.epi>");
  process.exit(2);
}

const bytes = new Uint8Array(fs.readFileSync(target));
const blob = {
  arrayBuffer: async () =>
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  name: path.basename(target),
};

const r = await sandbox.window.verifyEPI(blob);
console.log(
  JSON.stringify({
    structure: r.structure,
    manifest: r.manifest,
    integrity: r.integrity,
    signature: r.signature,
    trust_level: r.trust_level,
    mismatches: (r.mismatches || []).length,
    message: r.message,
  })
);
