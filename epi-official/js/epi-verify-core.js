/**
 * Browser .epi verifier for epilabs.org/verify/ and homepage drop-zone.
 * Classic script (no ES modules). Exposes window.verifyEPI(File|Blob)
 * and window.epiExtractZipBytes / window.epiDetectContainer.
 *
 * Supports:
 *  - envelope-v2 polyglot (magic "<!--" + 128-byte header + optional HTML + ZIP)
 *  - legacy ZIP .epi (starts with PK)
 *  - UTF-8 BOM / small leading junk before magic
 *  - ZIP payload located via EPI_ZIP_PAYLOAD_START marker (never via naive first-PK scan;
 *    embedded JSZip source can contain a false PK\x03\x04 string)
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

  function toU8(input) {
    if (!input) return new Uint8Array(0);
    if (input instanceof Uint8Array) return input;
    if (input instanceof ArrayBuffer) return new Uint8Array(input);
    if (ArrayBuffer.isView(input)) {
      return new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
    }
    return new Uint8Array(input);
  }

  function hexPreview(u8, n) {
    n = Math.min(n || 16, u8.length);
    var parts = [];
    for (var i = 0; i < n; i++) parts.push(u8[i].toString(16).padStart(2, '0'));
    return parts.join(' ');
  }

  function skipPreamble(u8) {
    var i = 0;
    // UTF-8 BOM
    if (u8.length >= 3 && u8[0] === 0xef && u8[1] === 0xbb && u8[2] === 0xbf) i = 3;
    // Leading CR/LF/TAB/SPACE only (never skip into binary header body)
    while (i < u8.length && (u8[i] === 0x09 || u8[i] === 0x0a || u8[i] === 0x0d || u8[i] === 0x20)) i++;
    return i;
  }

  function isEnvelopeMagicAt(u8, i) {
    return (
      i + 3 < u8.length &&
      u8[i] === 0x3c && // <
      u8[i + 1] === 0x21 && // !
      u8[i + 2] === 0x2d && // -
      u8[i + 3] === 0x2d // -
    );
  }

  function isZipMagicAt(u8, i) {
    // Local file header, empty archive, or spanning marker
    return (
      i + 1 < u8.length &&
      u8[i] === 0x50 &&
      u8[i + 1] === 0x4b &&
      (i + 3 >= u8.length ||
        u8[i + 2] === 0x03 ||
        u8[i + 2] === 0x05 ||
        u8[i + 2] === 0x07 ||
        u8[i + 2] === 0x00)
    );
  }

  function findBytes(u8, needle, from, to) {
    from = from || 0;
    to = to == null ? u8.length : to;
    if (typeof needle === 'string') needle = new TextEncoder().encode(needle);
    var end = Math.min(u8.length, to) - needle.length;
    outer: for (var i = from; i <= end; i++) {
      for (var j = 0; j < needle.length; j++) {
        if (u8[i + j] !== needle[j]) continue outer;
      }
      return i;
    }
    return -1;
  }

  /**
   * Detect container kind. Returns { format, offset } or null.
   * format: 'envelope-v2' | 'legacy-zip'
   */
  function detectContainer(input) {
    var u8 = toU8(input);
    if (u8.length < 4) return null;

    var pre = skipPreamble(u8);
    if (isEnvelopeMagicAt(u8, pre)) return { format: 'envelope-v2', offset: pre };
    if (isZipMagicAt(u8, pre)) return { format: 'legacy-zip', offset: pre };

    // Tolerate small leading junk (email/gateway wrappers, extra BOMs)
    var scanEnd = Math.min(u8.length - 4, pre + 512);
    for (var i = pre; i <= scanEnd; i++) {
      if (isEnvelopeMagicAt(u8, i)) return { format: 'envelope-v2', offset: i };
      if (isZipMagicAt(u8, i)) return { format: 'legacy-zip', offset: i };
    }

    // Marker present ⇒ envelope even if leading bytes were mangled
    var markerAt = findBytes(u8, EPI_ZIP_MARKER, 0, Math.min(u8.length, 8 * 1024 * 1024));
    if (markerAt >= 0) return { format: 'envelope-v2', offset: Math.max(0, markerAt - HEADER_SIZE) };

    return null;
  }

  function readPayloadLength(u8, headerOffset) {
    var view = new DataView(u8.buffer, u8.byteOffset + headerOffset, Math.min(HEADER_SIZE, u8.length - headerOffset));
    // uint64 LE at header offset + 8
    var lo = view.getUint32(8, true);
    var hi = view.getUint32(12, true);
    return lo + hi * 4294967296;
  }

  function extractEnvelopeZip(u8, headerOffset) {
    headerOffset = headerOffset || 0;
    if (u8.length < headerOffset + HEADER_SIZE) {
      throw new Error('EPI envelope header truncated');
    }

    var payloadLength = 0;
    try {
      payloadLength = readPayloadLength(u8, headerOffset);
    } catch (_e) {
      payloadLength = 0;
    }

    // Prefer the official payload sentinel (avoids false PK inside inlined JSZip).
    var scanFrom = headerOffset + HEADER_SIZE;
    var scanTo = Math.min(u8.length, scanFrom + 8 * 1024 * 1024);
    var markerAt = findBytes(u8, EPI_ZIP_MARKER, scanFrom, scanTo);
    var zipStart;
    if (markerAt >= 0) {
      zipStart = markerAt + EPI_ZIP_MARKER.length;
    } else {
      // No viewer shell — payload immediately after 128-byte header
      zipStart = headerOffset + HEADER_SIZE;
    }

    if (payloadLength > 0 && zipStart + payloadLength <= u8.length) {
      var slice = u8.slice(zipStart, zipStart + payloadLength);
      if (slice.length >= 2 && slice[0] === 0x50 && slice[1] === 0x4b) return slice;
    }

    // Length missing/wrong: take from zipStart if it looks like ZIP
    if (zipStart + 4 <= u8.length && u8[zipStart] === 0x50 && u8[zipStart + 1] === 0x4b) {
      return u8.slice(zipStart);
    }

    // Last resort after marker: search forward for a real local-file header,
    // but only after the marker (never in viewer HTML / JSZip source).
    var searchFrom = markerAt >= 0 ? markerAt + EPI_ZIP_MARKER.length : headerOffset + HEADER_SIZE;
    for (var i = searchFrom; i + 4 <= u8.length; i++) {
      if (u8[i] === 0x50 && u8[i + 1] === 0x4b && u8[i + 2] === 0x03 && u8[i + 3] === 0x04) {
        return u8.slice(i);
      }
    }

    throw new Error('EPI envelope ZIP payload not found after header/marker');
  }

  function extractZipBytes(input) {
    var u8 = toU8(input);
    if (!u8 || u8.length < 4) {
      throw new Error('File too small to be a valid .epi');
    }

    var det = detectContainer(u8);
    if (!det) {
      // Helpful diagnostics for HTML 404 pages, text files, etc.
      var pre = skipPreamble(u8);
      if (u8[pre] === 0x3c && u8[pre + 1] === 0x21 && u8[pre + 2] === 0x44) {
        throw new Error(
          'Not a valid .epi file — this looks like an HTML page (e.g. a broken download link), not a sealed artifact. First bytes: ' +
            hexPreview(u8, 16)
        );
      }
      throw new Error(
        'Not a valid .epi file (expected envelope-v2 magic "<!--" or ZIP "PK"). First bytes: ' +
          hexPreview(u8, 16)
      );
    }

    if (det.format === 'legacy-zip') {
      return det.offset === 0 ? u8 : u8.slice(det.offset);
    }

    return extractEnvelopeZip(u8, det.offset);
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

  function isPreJcsSpec(sv) {
    var s = String(sv || '').replace(/^v/i, '');
    var a = s.split(/[^\d]+/).map(function (x) { return parseInt(x, 10) || 0; });
    var maj = a[0] || 0, min = a[1] || 0, pat = a[2] || 0;
    if (maj <= 1) return false;
    if (maj !== 4) return maj < 4;
    if (min !== 4) return min < 4;
    return pat < 1;
  }

  function prepareManifestCopy(manifest) {
    var copy = JSON.parse(JSON.stringify(manifest));
    delete copy.signature;
    if (copy.content_truncated === null || copy.content_truncated === undefined) {
      delete copy.content_truncated;
    }
    if (copy.policy_load_status === null || copy.policy_load_status === undefined) {
      delete copy.policy_load_status;
    }
    return copy;
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
      var actualHash;
      try {
        var contentBuffer = await fileInZip.async('arraybuffer');
        actualHash = await sha256Hex(contentBuffer);
      } catch (e) {
        // Corrupt member (bad CRC / deflate stream): treat as mismatch,
        // never let the whole verification throw.
        mismatches.push(filename + ': unreadable/corrupt (' + (e && e.message ? e.message : 'decompression failed') + ')');
        continue;
      }
      if (actualHash !== expectedHash) {
        mismatches.push(filename + ': hash mismatch');
      }
    }
    return mismatches;
  }

  async function verifyManifestSignature(manifest, rawText) {
    if (!manifest || !manifest.signature) {
      return { valid: null, reason: 'No signature present' };
    }
    if (!manifest.public_key) {
      return { valid: false, reason: 'Missing public_key' };
    }
    if (typeof global.epiComputeManifestHash !== 'function' || typeof global.epiVerifyEd25519 !== 'function') {
      return { valid: null, reason: 'epi-manifest-preimage.js not loaded' };
    }
    var hashHex = await global.epiComputeManifestHash(rawText || JSON.stringify(manifest));
    var r = await global.epiVerifyEd25519(manifest.signature, manifest.public_key, hashHex);
    return { valid: r.valid, reason: r.msg };
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

    var rawManifest;
    var manifest;
    try {
      rawManifest = await mFile.async('string');
      manifest = JSON.parse(rawManifest);
    } catch (_e) {
      return {
        structure: true, manifest: false, integrity: false, hashChain: false,
        signature: false, hash: null, trust_level: 'NONE', identity: 'UNKNOWN',
        message: 'manifest.json is not valid JSON', mismatches: []
      };
    }

    var mismatches = await computeIntegrityMismatches(zip, manifest);
    var integrity = mismatches.length === 0;
    var sigResult = await verifyManifestSignature(manifest, rawManifest);
    var fileHash = await sha256Hex(ab);

    var trust_level = 'NONE';
    var identity = 'UNKNOWN';
    var message = '';
    if (!integrity) {
      trust_level = 'NONE';
      message = 'Integrity failed - do not trust';
    } else if (sigResult.valid === false) {
      trust_level = 'NONE';
      message = 'Signature invalid - do not trust';
    } else if (sigResult.valid === true) {
      trust_level = 'UNVERIFIED_IDENTITY';
      identity = 'UNKNOWN';
      message = 'Seal valid · identity not pinned — not claim-ready. Use epi keys trust + epi verify --policy strict';
    } else if (!manifest.signature) {
      trust_level = 'MEDIUM';
      identity = 'NONE';
      message = 'Unsigned - integrity intact';
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
  global.epiDetectContainer = detectContainer;
  global.epiIsPreJcsSpec = isPreJcsSpec;
  if (typeof window !== 'undefined') {
    window.verifyEPI = verifyEPI;
    window.epiExtractZipBytes = extractZipBytes;
    window.epiDetectContainer = detectContainer;
  }
})(typeof window !== 'undefined' ? window : globalThis);
