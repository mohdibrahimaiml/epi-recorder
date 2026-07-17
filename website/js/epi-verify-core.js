import * as ed from 'https://esm.sh/@noble/ed25519@2.0.0';

function requireJsZip() {
  if (!globalThis.JSZip) {
    throw new Error('JSZip is required to read .epi files in the browser.');
  }
  return globalThis.JSZip;
}

function normalizeDatetime(value) {
  if (typeof value !== 'string') {
    return value;
  }
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) {
    return value;
  }
  let normalized = value.replace(/\.\d+/, '');
  if (!normalized.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(normalized)) {
    normalized += 'Z';
  }
  return normalized;
}

function canonicalJson(value) {
  if (value === null) {
    return 'null';
  }
  if (typeof value === 'string') {
    return JSON.stringify(normalizeDatetime(value));
  }
  if (typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return '[' + value.map((item) => canonicalJson(item)).join(',') + ']';
  }
  const keys = Object.keys(value).sort();
  return '{' + keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',') + '}';
}

function hexToBytes(hex) {
  if (typeof hex !== 'string' || hex.length % 2 !== 0) {
    throw new Error('Invalid hex string.');
  }
  const bytes = new Uint8Array(hex.length / 2);
  for (let index = 0; index < hex.length; index += 2) {
    const byte = Number.parseInt(hex.slice(index, index + 2), 16);
    if (Number.isNaN(byte)) {
      throw new Error('Invalid hex string.');
    }
    bytes[index / 2] = byte;
  }
  return bytes;
}

function base64ToBytes(value) {
  const binary = atob(String(value || '').replace(/\s+/g, ''));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function decodeHexOrBase64(value, label) {
  try {
    return hexToBytes(value);
  } catch (_hexError) {
    try {
      return base64ToBytes(value);
    } catch (_base64Error) {
      throw new Error(`Invalid ${label} encoding (not hex or base64).`);
    }
  }
}

async function sha256Hex(bufferLike) {
  const digest = await crypto.subtle.digest('SHA-256', bufferLike);
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function computeIntegrityMismatches(zip, manifest) {
  const mismatches = [];
  const fileManifest = manifest?.file_manifest || {};
  for (const [filename, expectedHash] of Object.entries(fileManifest)) {
    const fileInZip = zip.file(filename);
    if (!fileInZip) {
      mismatches.push(`${filename}: file missing`);
      continue;
    }
    const contentBuffer = await fileInZip.async('arraybuffer');
    const actualHash = await sha256Hex(contentBuffer);
    if (actualHash !== expectedHash) {
      mismatches.push(`${filename}: hash mismatch`);
    }
  }
  return mismatches;
}

function parseSteps(stepsText) {
  return String(stepsText || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch (_error) {
        return null;
      }
    })
    .filter(Boolean);
}

async function verifyManifestSignature(manifest, manualPublicKey) {
  if (!manifest.signature) {
    return {
      state: 'warning',
      signerLabel: 'Unsigned',
      description: 'Integrity is intact, but no signature is present. This artifact is unsigned.',
      signatureValid: null,
    };
  }

  const parts = String(manifest.signature).split(':');
  if (parts.length !== 3 || parts[0] !== 'ed25519') {
    throw new Error('Malformed signature string.');
  }

  const signerLabel = parts[1] || 'Unknown';
  const signatureBytes = decodeHexOrBase64(parts[2], 'signature');
  const verificationKeyValue = String(manualPublicKey || manifest.public_key || '').trim();
  if (!verificationKeyValue) {
    return {
      state: 'warning',
      signerLabel,
      description: 'Identity unverified. Provide a public key or use the embedded key to confirm origin.',
      signatureValid: false,
    };
  }

  const publicKeyBytes = decodeHexOrBase64(verificationKeyValue, 'public key');
  const manifestCopy = JSON.parse(JSON.stringify(manifest));
  delete manifestCopy.signature;
  const messageBytes = new TextEncoder().encode(canonicalJson(manifestCopy));
  const hashBytes = new Uint8Array(await crypto.subtle.digest('SHA-256', messageBytes));
  const isValid = await ed.verifyAsync(signatureBytes, hashBytes, publicKeyBytes);

  if (!isValid) {
    return {
      state: 'error',
      signerLabel,
      description: 'Signature verification failed. The artifact should not be trusted.',
      signatureValid: false,
    };
  }

  return {
    state: 'success',
    signerLabel,
    description: manualPublicKey
      ? 'Verified against the manually provided public key.'
      : 'Cryptographically verified with the public key embedded in the artifact.',
    signatureValid: true,
  };
}

export async function analyzeArtifactBlob(blob, options = {}) {
  const JSZip = requireJsZip();
  const zip = await JSZip.loadAsync(blob);
  const manifestFile = zip.file('manifest.json');
  if (!manifestFile) {
    throw new Error('Invalid .epi bundle: manifest.json missing');
  }

  const manifest = JSON.parse(await manifestFile.async('string'));
  const mismatches = await computeIntegrityMismatches(zip, manifest);
  const stepsFile = zip.file('steps.jsonl');
  const steps = stepsFile ? parseSteps(await stepsFile.async('string')) : [];
  const viewerFile = zip.file('viewer.html');
  const viewerHtml = options.allowEmbeddedViewer && viewerFile ? await viewerFile.async('string') : null;

  let verification;
  if (mismatches.length > 0) {
    verification = {
      state: 'tampered',
      signerLabel: manifest.signature ? String(manifest.signature).split(':')[1] || 'Unknown' : 'Unsigned',
      description: `Integrity failed: ${mismatches.length} manifest mismatch(es) detected.`,
      signatureValid: false,
    };
  } else {
    verification = await verifyManifestSignature(manifest, options.manualPublicKey || '');
  }

  return {
    manifest,
    mismatches,
    steps,
    fileManifest: manifest.file_manifest || {},
    viewerHtml,
    verification,
  };
}

export function openEmbeddedViewerHtml(htmlContent) {
  const blob = new Blob([htmlContent], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank', 'noopener,noreferrer');
}
