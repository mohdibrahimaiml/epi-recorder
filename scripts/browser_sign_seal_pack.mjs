#!/usr/bin/env node
/**
 * Headless Sign & Seal packer for regression tests.
 * Loads epi_viewer_static/crypto.js helpers and builds an envelope-v2 + signed .epi
 * the same way the browser Sign & Seal path does (ZIP + wrap + re-sign).
 *
 * Usage:
 *   node scripts/browser_sign_seal_pack.mjs --out path.epi [--seed-hex 64hex] [--no-polyglot]
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, randomBytes as nodeRandomBytes } from 'node:crypto';
import { deflateRawSync } from 'node:zlib';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');

// Minimal crypto.subtle polyfill surface used by crypto.js (SHA-256 / SHA-512).
if (!globalThis.crypto) {
  globalThis.crypto = {};
}
if (!globalThis.crypto.subtle) {
  globalThis.crypto.subtle = {
    digest: async (algo, data) => {
      const name = String(algo).toUpperCase().replace('-', '');
      const h = createHash(name === 'SHA512' ? 'sha512' : 'sha256');
      h.update(Buffer.from(data instanceof ArrayBuffer ? new Uint8Array(data) : data));
      return h.digest().buffer;
    },
  };
}
if (!globalThis.crypto.getRandomValues) {
  globalThis.crypto.getRandomValues = (arr) => {
    const buf = nodeRandomBytes(arr.length);
    arr.set(buf);
    return arr;
  };
}

// Evaluate crypto.js into this global scope (defines noble + epi* helpers).
const cryptoJs = readFileSync(resolve(ROOT, 'epi_viewer_static/crypto.js'), 'utf8');
// crypto.js assigns globalThis.noble and functions; run as script.
const run = new Function(cryptoJs + '\n;return { noble: globalThis.noble, epiWrapEnvelopeV2, epiSignManifest, epiPackEnvelopeHeader, EPI_LEGACY_MIMETYPE };');
// Ensure globalThis bindings exist for code that references bare identifiers in some envs
globalThis.globalThis = globalThis;
eval(cryptoJs);

function parseArgs(argv) {
  const out = { out: null, seedHex: null, polyglot: true };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === '--out') out.out = argv[++i];
    else if (argv[i] === '--seed-hex') out.seedHex = argv[++i];
    else if (argv[i] === '--no-polyglot') out.polyglot = false;
  }
  if (!out.out) {
    console.error('Usage: node scripts/browser_sign_seal_pack.mjs --out file.epi [--seed-hex 64hex]');
    process.exit(2);
  }
  return out;
}

// --- minimal ZIP writer (store or deflate) ---------------------------------
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function zipStore(entries) {
  // entries: [{name, data:Uint8Array, store?:bool}]
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const ent of entries) {
    const name = Buffer.from(ent.name, 'utf8');
    const data = Buffer.from(ent.data);
    const useStore = ent.store || ent.name === 'mimetype';
    const compressed = useStore ? data : deflateRawSync(data);
    const method = useStore ? 0 : 8;
    const crc = crc32(data);
    const local = Buffer.alloc(30 + name.length);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 6);
    local.writeUInt16LE(method, 8);
    local.writeUInt16LE(0, 10);
    local.writeUInt16LE(0, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(compressed.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    local.writeUInt16LE(0, 28);
    name.copy(local, 30);
    locals.push(local, compressed);

    const central = Buffer.alloc(46 + name.length);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0, 8);
    central.writeUInt16LE(method, 10);
    central.writeUInt16LE(0, 12);
    central.writeUInt16LE(0, 14);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(compressed.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt16LE(0, 30);
    central.writeUInt16LE(0, 32);
    central.writeUInt16LE(0, 34);
    central.writeUInt16LE(0, 36);
    central.writeUInt32LE(0, 38);
    central.writeUInt32LE(offset, 42);
    name.copy(central, 46);
    centrals.push(central);
    offset += local.length + compressed.length;
  }
  const centralSize = centrals.reduce((s, b) => s + b.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(0, 4);
  end.writeUInt16LE(0, 6);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(offset, 16);
  end.writeUInt16LE(0, 20);
  return Buffer.concat([...locals, ...centrals, end]);
}

function sha256Hex(buf) {
  return createHash('sha256').update(buf).digest('hex');
}

async function main() {
  const args = parseArgs(process.argv);
  if (typeof epiWrapEnvelopeV2 !== 'function' || typeof epiSignManifest !== 'function') {
    throw new Error('crypto.js helpers not loaded');
  }

  const seed = args.seedHex
    ? noble.etc.hexToBytes(args.seedHex)
    : noble.etc.randomBytes(32);

  const workflowId = '550e8400-e29b-41d4-a716-446655440000';
  const createdAt = '2026-01-15T12:00:00Z';
  const stepsJsonl = JSON.stringify({
    index: 0,
    timestamp: createdAt,
    content: { type: 'info', message: 'browser-seal-regression' },
  }) + '\n';
  const viewerHtml = '<!DOCTYPE html><html><head><title>EPI</title></head><body>reviewed</body></html>';
  const viewerHash = sha256Hex(Buffer.from(viewerHtml, 'utf8'));
  const stepsHash = sha256Hex(Buffer.from(stepsJsonl, 'utf8'));

  let manifest = {
    spec_version: '4.0.1',
    workflow_id: workflowId,
    created_at: createdAt,
    container_format: 'envelope-v2',
    file_manifest: {
      'steps.jsonl': stepsHash,
      'viewer.html': viewerHash,
    },
    cli_command: 'browser-sign-seal-pack',
  };

  manifest = await epiSignManifest(manifest, seed);

  const zipBuf = zipStore([
    { name: 'mimetype', data: Buffer.from(EPI_LEGACY_MIMETYPE || 'application/vnd.epi+zip'), store: true },
    { name: 'steps.jsonl', data: Buffer.from(stepsJsonl, 'utf8') },
    { name: 'viewer.html', data: Buffer.from(viewerHtml, 'utf8') },
    { name: 'manifest.json', data: Buffer.from(JSON.stringify(manifest, null, 2), 'utf8') },
  ]);

  const envelope = await epiWrapEnvelopeV2(
    new Uint8Array(zipBuf),
    manifest,
    args.polyglot ? viewerHtml : null,
  );

  const outPath = resolve(args.out);
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, Buffer.from(envelope));

  // Print header hex (first 128 bytes) for comparison tooling
  const headerHex = Buffer.from(envelope.slice(0, 128)).toString('hex');
  console.log(JSON.stringify({
    out: outPath,
    size: envelope.length,
    magic: Buffer.from(envelope.slice(0, 4)).toString('ascii'),
    header_hex: headerHex,
    has_signature: Boolean(manifest.signature),
    public_key: manifest.public_key,
    signature_prefix: String(manifest.signature || '').slice(0, 40),
  }, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
