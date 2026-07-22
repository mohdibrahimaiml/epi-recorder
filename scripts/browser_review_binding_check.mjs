#!/usr/bin/env node
/**
 * Compare JS epiBuildArtifactBinding against a JSON fixture produced by Python.
 * Usage: node scripts/browser_review_binding_check.mjs --fixture path.json
 * Fixture shape: { binding: {...}, members: { path: base64, ... }, manifest_path: "manifest.json",
 *   workflow_id, manifest_signature, manifest_public_key, container_format, file_manifest_paths: [] }
 */
import { readFileSync } from 'node:fs';
import { createHash, randomBytes, webcrypto } from 'node:crypto';
import { resolve } from 'node:path';

if (!globalThis.crypto) globalThis.crypto = webcrypto;
if (!globalThis.crypto.getRandomValues) {
  globalThis.crypto.getRandomValues = (a) => {
    a.set(randomBytes(a.length));
    return a;
  };
}

const ROOT = resolve(import.meta.dirname || new URL('.', import.meta.url).pathname, '..');
const cryptoJs = readFileSync(resolve(ROOT, 'epi_viewer_static/crypto.js'), 'utf8');
(0, eval)(cryptoJs);

function parseArgs(argv) {
  let fixture = null;
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === '--fixture') fixture = argv[++i];
  }
  if (!fixture) {
    console.error('Usage: node scripts/browser_review_binding_check.mjs --fixture fixture.json');
    process.exit(2);
  }
  return { fixture };
}

async function main() {
  const { fixture } = parseArgs(process.argv);
  const data = JSON.parse(readFileSync(fixture, 'utf8'));
  const memberBytesByPath = {};
  for (const [path, b64] of Object.entries(data.members || {})) {
    memberBytesByPath[path] = new Uint8Array(Buffer.from(b64, 'base64'));
  }
  const manifestBytes = memberBytesByPath[data.manifest_path || 'manifest.json'];
  if (!manifestBytes) throw new Error('manifest bytes missing in fixture');

  const binding = await epiBuildArtifactBinding({
    workflowId: data.workflow_id,
    manifestBytes,
    manifestSignature: data.manifest_signature,
    manifestPublicKey: data.manifest_public_key,
    fileManifestPaths: data.file_manifest_paths,
    memberBytesByPath,
    containerFormat: data.container_format,
  });

  const expected = data.binding;
  const ok = JSON.stringify(binding) === JSON.stringify(expected);
  console.log(JSON.stringify({ ok, binding, expected }, null, 2));
  process.exit(ok ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
