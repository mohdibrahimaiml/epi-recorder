/* Verify a .epi with the browser verifier (website/js/epi-verify-core.js) under Node.
 *
 * Usage: node verify_epi_node.mjs <file.epi>
 * Prints a JSON object: {structure, manifest, integrity, signature, trust_level,
 * mismatches, mismatch_detail, message}. Exit code 0 on success, non-zero on
 * loader failure.
 *
 * The scripts run in the HOST realm (indirect eval), not a `vm` sandbox: JSZip
 * hands its ArrayBuffers to `crypto.subtle.digest`, and a `vm` sandbox is a
 * separate realm whose ArrayBuffer fails Node 20's WebCrypto brand check
 * ("2nd argument is not instance of ArrayBuffer…") even though the bytes are
 * identical. Node 24 happens to tolerate the cross-realm buffer; Node 20 does
 * not. One realm avoids the problem entirely.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(here, "..", "..");
const WEB = path.join(REPO, "website");

globalThis.window = globalThis;
globalThis.self = globalThis;

for (const rel of ["js/jszip.min.js", "js/epi-verify-core.js"]) {
  // eslint-disable-next-line no-eval
  (0, eval)(fs.readFileSync(path.join(WEB, rel), "utf8"));
}

const verifyEPI = globalThis.verifyEPI;
if (typeof verifyEPI !== "function") {
  console.error("verifyEPI not exposed by epi-verify-core.js");
  process.exit(3);
}

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

const r = await verifyEPI(blob);
console.log(
  JSON.stringify({
    structure: r.structure,
    manifest: r.manifest,
    integrity: r.integrity,
    signature: r.signature,
    trust_level: r.trust_level,
    mismatches: (r.mismatches || []).length,
    mismatch_detail: (r.mismatches || []).slice(0, 10),
    message: r.message,
  })
);
