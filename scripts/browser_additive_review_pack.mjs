#!/usr/bin/env node
/**
 * Model A: attach v1.1 signed review to an existing .epi without re-signing the manifest.
 * Usage:
 *   node scripts/browser_additive_review_pack.mjs --in in.epi --out out.epi \
 *     --seed-hex 64hex --reviewer name --status approved --notes "..."
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { createHash, randomBytes, webcrypto } from 'node:crypto';
import { deflateRawSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');

if (!globalThis.crypto) globalThis.crypto = webcrypto;
if (!globalThis.crypto.subtle) {
  Object.defineProperty(globalThis.crypto, 'subtle', {
    value: {
      digest: async (algo, data) => {
        const name = String(algo).toUpperCase().includes('512') ? 'sha512' : 'sha256';
        return createHash(name)
          .update(Buffer.from(data instanceof ArrayBuffer ? new Uint8Array(data) : data))
          .digest().buffer;
      },
    },
  });
}
if (!globalThis.crypto.getRandomValues) {
  globalThis.crypto.getRandomValues = (a) => {
    a.set(randomBytes(a.length));
    return a;
  };
}

const cryptoJs = readFileSync(resolve(ROOT, 'epi_viewer_static/crypto.js'), 'utf8');
(0, eval)(cryptoJs);

// Minimal ZIP reader/writer for STORE+DEFLATE copy
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  }
  return (c ^ 0xffffffff) >>> 0;
}

import { inflateRawSync } from 'node:zlib';

function readZipEntriesSync(zipBuf) {
  const buf = Buffer.from(zipBuf);
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new Error('EOCD not found');
  const centralOffset = buf.readUInt32LE(eocd + 16);
  const entryCount = buf.readUInt16LE(eocd + 10);
  const entries = [];
  let off = centralOffset;
  for (let n = 0; n < entryCount; n++) {
    if (buf.readUInt32LE(off) !== 0x02014b50) throw new Error('bad central header at ' + off);
    const nameLen = buf.readUInt16LE(off + 28);
    const extraLen = buf.readUInt16LE(off + 30);
    const commentLen = buf.readUInt16LE(off + 32);
    const localOff = buf.readUInt32LE(off + 42);
    const name = buf.slice(off + 46, off + 46 + nameLen).toString('utf8');
    off += 46 + nameLen + extraLen + commentLen;

    if (buf.readUInt32LE(localOff) !== 0x04034b50) throw new Error('bad local header ' + name);
    const localMethod = buf.readUInt16LE(localOff + 8);
    const localComp = buf.readUInt32LE(localOff + 18);
    const localNameLen = buf.readUInt16LE(localOff + 26);
    const localExtra = buf.readUInt16LE(localOff + 28);
    const dataStart = localOff + 30 + localNameLen + localExtra;
    const compressed = buf.slice(dataStart, dataStart + localComp);
    let data;
    if (localMethod === 0) data = Buffer.from(compressed);
    else if (localMethod === 8) data = inflateRawSync(compressed);
    else throw new Error('unsupported zip method ' + localMethod + ' for ' + name);
    entries.push({ name, data: new Uint8Array(data) });
  }
  return entries;
}

function writeZip(entries) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const ent of entries) {
    const name = Buffer.from(ent.name, 'utf8');
    const data = Buffer.from(ent.data);
    const useStore = ent.name === 'mimetype' || ent.store;
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

function parseArgs(argv) {
  const o = {
    in: null,
    out: null,
    seedHex: null,
    reviewer: 'reviewer',
    status: 'approved',
    notes: '',
  };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === '--in') o.in = argv[++i];
    else if (argv[i] === '--out') o.out = argv[++i];
    else if (argv[i] === '--seed-hex') o.seedHex = argv[++i];
    else if (argv[i] === '--reviewer') o.reviewer = argv[++i];
    else if (argv[i] === '--status') o.status = argv[++i];
    else if (argv[i] === '--notes') o.notes = argv[++i];
  }
  if (!o.in || !o.out || !o.seedHex) {
    console.error('Need --in --out --seed-hex');
    process.exit(2);
  }
  return o;
}

async function main() {
  const args = parseArgs(process.argv);
  const epiBytes = new Uint8Array(readFileSync(resolve(args.in)));
  const { zipBytes, containerFormat } = epiExtractInnerZipFromEpi(epiBytes);
  const entries = readZipEntriesSync(zipBytes);
  const byName = Object.fromEntries(entries.map((e) => [e.name, e.data]));

  if (!byName['manifest.json']) throw new Error('manifest.json missing');
  const manifestText = Buffer.from(byName['manifest.json']).toString('utf8');
  const manifest = JSON.parse(manifestText);
  const paths = Object.keys(manifest.file_manifest || {}).sort();

  const binding = await epiBuildArtifactBinding({
    workflowId: manifest.workflow_id,
    manifestBytes: byName['manifest.json'],
    manifestSignature: manifest.signature,
    manifestPublicKey: manifest.public_key,
    fileManifestPaths: paths,
    memberBytesByPath: byName,
    containerFormat,
  });

  const seed = noble.etc.hexToBytes(args.seedHex);
  const built = await epiBuildSignedReviewRecord({
    reviewedBy: args.reviewer,
    reviewedAt: new Date().toISOString(),
    humanStatus: args.status,
    notes: args.notes,
    artifactBinding: binding,
    previousReviewHash: null,
    seedBytes: seed,
  });

  const record = built.record;
  const reviewPath = 'reviews/' + record.review_id + '.json';
  const reviewJson = new TextEncoder().encode(JSON.stringify(record, null, 2));
  const latestJson = reviewJson;
  const index = epiBuildReviewIndex([record], record.review_id);
  const indexJson = new TextEncoder().encode(JSON.stringify(index, null, 2));

  const skip = new Set(['review.json', 'review_index.json']);
  const next = entries
    .filter((e) => !skip.has(e.name) && !e.name.startsWith('reviews/'))
    .map((e) => ({ name: e.name, data: e.data, store: e.name === 'mimetype' }));
  next.push({ name: reviewPath, data: reviewJson });
  next.push({ name: 'review.json', data: latestJson });
  next.push({ name: 'review_index.json', data: indexJson });
  // mimetype first
  next.sort((a, b) => {
    if (a.name === 'mimetype') return -1;
    if (b.name === 'mimetype') return 1;
    return a.name.localeCompare(b.name);
  });

  const newZip = writeZip(next);
  let outBytes;
  if (containerFormat === 'legacy-zip') {
    outBytes = newZip;
  } else {
    outBytes = await epiWrapEnvelopeV2(new Uint8Array(newZip), manifest, null);
  }

  const outPath = resolve(args.out);
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, Buffer.from(outBytes));
  console.log(
    JSON.stringify(
      {
        out: outPath,
        review_id: record.review_id,
        review_version: record.review_version,
        binding_sealed: binding.sealed_evidence_sha256,
        original_signature: manifest.signature,
        review_signature_prefix: String(record.review_signature || '').slice(0, 40),
      },
      null,
      2,
    ),
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
