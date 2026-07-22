/**
 * Browser .epi verifier for epilabs.org/verify/
 * Classic script (no ES modules). Exposes window.verifyEPI(File|Blob).
 * Supports envelope-v2 (magic "<!--") and legacy ZIP.
 */
(function (global) {
  'use strict';

  var EPI_ZIP_MARKER = '\n<!-- EPI_ZIP_PAYLOAD_START -->\n';
  var HEADER_SIZE = 128;

  function requireJsZip() {
    if (!global.JSZip) {
      throw new Error('JSZip is required. Check that jszip.min.js loaded.');
    }
    return global.JSZip;
  }

  function normalizeDatetime(value) {
    if (typeof value !== 'string') return value;
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) return value;
    var normalized = value.replace(/\.\d+/, '');
    if (!normalized.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(normalized)) normalized += 'Z';
    return normalized;
  }

  function canonicalJson(value) {
    if (value === null) return 'null';
    if (typeof value === 'string') return JSON.stringify(normalizeDatetime(value));
    if (typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
    var keys = Object.keys(value).sort();
    return '{' + keys.map(function (k) {
      return JSON.stringify(k) + ':' + canonicalJson(value[k]);
    }).join(',') + '}';
  }

  function hexToBytes(hex) {
    if (typeof hex !== 'string' || hex.length % 2 !== 0) throw new Error('Invalid hex');
    var bytes = new Uint8Array(hex.length / 2);
    for (var i = 0; i < hex.length; i += 2) {
      bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
    }
    return bytes;
  }

  function base64ToBytes(value) {
    var binary = atob(String(value || '').replace(/\s+/g, ''));
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  function decodeSig(value) {
    try {
      return hexToBytes(value);
    } catch (_e) {
      return base64ToBytes(value);
    }
  }

  async function sha256Hex(bufferLike) {
    var digest = await crypto.subtle.digest('SHA-256', bufferLike);
    return Array.from(new Uint8Array(digest)).map(function (b) {
      return b.toString(16).padStart(2, '0');
    }).join('');
  }

  function extractZipBytes(u8) {
    if (!u8 || u8.length < 4) throw new Error('File too small to be a valid .epi');
    if (u8[0] === 0x3c && u8[1] === 0x21 && u8[2] === 0x2d && u8[3] === 0x2d) {
      if (u8.length < HEADER_SIZE) throw new Error('EPI envelope header truncated');
      var view = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
      var payloadLength = view.getUint32(8, true) + view.getUint32(12, true) * 4294967296;
      var markerBytes = new TextEncoder().encode(EPI_ZIP_MARKER);
      var zipStart = HEADER_SIZE;
      var scanEnd = Math.min(u8.length, HEADER_SIZE + 4 * 1024 * 1024);
      for (var i = HEADER_SIZE; i + markerBytes.length <= scanEnd; i++) {
        var match = true;
        for (var j = 0; j < markerBytes.length; j++) {
          if (u8[i + j] !== markerBytes[j]) { match = false; break; }
        }
        if (match) {
          zipStart = i + markerBytes.length;
          break;
        }
      }
      if (zipStart + payloadLength > u8.length) {
        throw new Error('EPI envelope payload truncated');
      }
      return u8.slice(zipStart, zipStart + payloadLength);
    }
    if (u8[0] === 0x50 && u8[1] === 0x4b) {
      return u8;
    }
    throw new Error('Not a valid .epi file (expected envelope-v2 or ZIP)');
  }

  async function computeIntegrityMismatches(zip, manifest) {
    var mismatches = [];
    var fileManifest = (manifest && manifest.file_manifest) || {};
    var names = Object.keys(fileManifest);
    for (var n = 0; n < names.length; n++) {
      var filename = names[n];
      var expectedHash = fileManifest[filename];
      var fileInZip = zip.file(filename);
      if (!fileInZip) {
        mismatches.push(filename + ': file missing');
        continue;
      }
      var contentBuffer = await fileInZip.async('arraybuffer');
      var actualHash = await sha256Hex(contentBuffer);
      if (actualHash !== expectedHash) {
        mismatches.push(filename + ': hash mismatch');
      }
    }
    return mismatches;
  }

  async function verifyManifestSignature(manifest) {
    if (!manifest || !manifest.signature) {
      return { valid: null, reason: 'No signature present' };
    }
    if (!manifest.public_key) {
      return { valid: false, reason: 'Missing public_key' };
    }
    var parts = String(manifest.signature).split(':');
    if (parts.length !== 3 || parts[0] !== 'ed25519') {
      return { valid: false, reason: 'Invalid signature format' };
    }
    var sigHex = parts[2];
    var copy = JSON.parse(JSON.stringify(manifest));
    delete copy.signature;
    var msg = new TextEncoder().encode(canonicalJson(copy));
    var hashBuf = await crypto.subtle.digest('SHA-256', msg);
    var hashBytes = new Uint8Array(hashBuf);
    var pubBytes = hexToBytes(manifest.public_key);
    var sigBytes = decodeSig(sigHex);

    try {
      if (crypto.subtle && crypto.subtle.importKey) {
        var key = await crypto.subtle.importKey('raw', pubBytes, { name: 'Ed25519' }, false, ['verify']);
        var ok = await crypto.subtle.verify({ name: 'Ed25519' }, key, sigBytes, hashBytes);
        return { valid: ok, reason: ok ? 'Ed25519 valid' : 'Signature mismatch' };
      }
    } catch (_webcryptoErr) {
      /* fall through */
    }

    if (global.noble && global.noble.verifyAsync) {
      try {
        var ok2 = await global.noble.verifyAsync(sigBytes, hashBytes, pubBytes);
        return { valid: !!ok2, reason: ok2 ? 'Ed25519 valid (noble)' : 'Signature mismatch' };
      } catch (e) {
        return { valid: false, reason: e.message || 'Verify failed' };
      }
    }

    return { valid: null, reason: 'Browser cannot verify Ed25519 (try Chrome/Edge or: epi verify)' };
  }

  async function verifyEPI(file) {
    var JSZip = requireJsZip();
    var ab = await file.arrayBuffer();
    var u8 = new Uint8Array(ab);
    var zipBytes;
    try {
      zipBytes = extractZipBytes(u8);
    } catch (e) {
      return {
        structure: false, manifest: false, integrity: false, hashChain: false,
        signature: false, hash: null, trust_level: 'NONE', identity: 'UNKNOWN',
        message: e.message || 'Invalid container', mismatches: []
      };
    }

    var zip;
    try {
      zip = await JSZip.loadAsync(zipBytes);
    } catch (e) {
      return {
        structure: false, manifest: false, integrity: false, hashChain: false,
        signature: false, hash: null, trust_level: 'NONE', identity: 'UNKNOWN',
        message: 'ZIP payload unreadable: ' + (e.message || e), mismatches: []
      };
    }

    var mFile = zip.file('manifest.json');
    if (!mFile) {
      return {
        structure: true, manifest: false, integrity: false, hashChain: false,
        signature: false, hash: null, trust_level: 'NONE', identity: 'UNKNOWN',
        message: 'manifest.json missing', mismatches: []
      };
    }

    var manifest;
    try {
      manifest = JSON.parse(await mFile.async('string'));
    } catch (_e) {
      return {
        structure: true, manifest: false, integrity: false, hashChain: false,
        signature: false, hash: null, trust_level: 'NONE', identity: 'UNKNOWN',
        message: 'manifest.json is not valid JSON', mismatches: []
      };
    }

    var mismatches = await computeIntegrityMismatches(zip, manifest);
    var integrity = mismatches.length === 0;
    var sigResult = await verifyManifestSignature(manifest);
    var fileHash = await sha256Hex(ab);

    var trust_level = 'NONE';
    var identity = 'UNKNOWN';
    var message = '';
    if (!integrity) {
      trust_level = 'NONE';
      message = 'Integrity failed — do not trust';
    } else if (sigResult.valid === false) {
      trust_level = 'NONE';
      message = 'Signature invalid — do not trust';
    } else if (sigResult.valid === true) {
      trust_level = 'LOW';
      identity = 'UNKNOWN';
      message = 'Valid signature; identity unknown in browser (use epi keys trust + epi verify for HIGH)';
    } else if (!manifest.signature) {
      trust_level = 'MEDIUM';
      identity = 'NONE';
      message = 'Unsigned — integrity intact';
    } else {
      trust_level = 'LOW';
      message = sigResult.reason || 'Signature check incomplete in this browser';
    }

    return {
      structure: true,
      manifest: true,
      integrity: integrity,
      hashChain: true,
      signature: sigResult.valid,
      hash: fileHash,
      trust_level: trust_level,
      identity: identity,
      message: message,
      mismatches: mismatches,
      signer: manifest.signature ? String(manifest.signature).split(':')[1] : null
    };
  }

  global.verifyEPI = verifyEPI;
  global.epiExtractZipBytes = extractZipBytes;
})(typeof window !== 'undefined' ? window : globalThis);
