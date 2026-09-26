/**
 * Shared Ed25519 preimage for the browser verifier (homepage, /verify/, Node CI).
 * Dispatch matches epi_core._version.JCS_INTRODUCED_TUPLE (4, 4, 1):
 *   spec < 4.4.1 → json.dumps(sort_keys) with preserved float text (900.0)
 *   spec >= 4.4.1 → JCS-equivalent JSON.parse numbers (900.0 → 900)
 * Omit null content_truncated, policy_load_status, producer_version (MANIFEST_OMIT_NONE_FROM_HASH).
 */
(function (global) {
  'use strict';

  function sha256(buf) {
    return crypto.subtle.digest('SHA-256', buf).then(function (h) {
      return Array.from(new Uint8Array(h)).map(function (b) {
        return b.toString(16).padStart(2, '0');
      }).join('');
    });
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

  function tokenizeJSON(str) {
    var tokens = [], i = 0;
    while (i < str.length) {
      var c = str[i];
      if (c === ' ' || c === '\t' || c === '\n' || c === '\r') { i++; continue; }
      if (c === '"') {
        i++; var s = '';
        while (i < str.length) {
          var ch = str[i];
          if (ch === '\\') {
            i++;
            var e = str[i];
            if (e === 'n') s += '\n';
            else if (e === 't') s += '\t';
            else if (e === 'r') s += '\r';
            else if (e === 'b') s += '\b';
            else if (e === 'f') s += '\f';
            else if (e === 'u') {
              s += String.fromCharCode(parseInt(str.substring(i + 1, i + 5), 16));
              i += 4;
            } else s += e;
            i++;
          } else if (ch === '"') { i++; break; }
          else { s += ch; i++; }
        }
        tokens.push({ type: 'string', value: s });
        continue;
      }
      if (c === '{' || c === '}' || c === '[' || c === ']' || c === ':' || c === ',') {
        tokens.push({ type: c }); i++; continue;
      }
      if (str.substring(i, i + 4) === 'true') { tokens.push({ type: 'true', value: true }); i += 4; continue; }
      if (str.substring(i, i + 5) === 'false') { tokens.push({ type: 'false', value: false }); i += 5; continue; }
      if (str.substring(i, i + 4) === 'null') { tokens.push({ type: 'null', value: null }); i += 4; continue; }
      if (c === '-' || (c >= '0' && c <= '9')) {
        var start = i;
        if (str[i] === '-') i++;
        while (i < str.length && str[i] >= '0' && str[i] <= '9') i++;
        if (str[i] === '.') { i++; while (i < str.length && str[i] >= '0' && str[i] <= '9') i++; }
        if (str[i] === 'e' || str[i] === 'E') {
          i++; if (str[i] === '+' || str[i] === '-') i++;
          while (i < str.length && str[i] >= '0' && str[i] <= '9') i++;
        }
        tokens.push({ type: 'number', raw: str.substring(start, i) });
        continue;
      }
      throw new Error('Unexpected character ' + c + ' at ' + i);
    }
    return tokens;
  }

  function parseJSONPreserveNumbers(text) {
    var tokens = tokenizeJSON(text), pos = 0;
    function parseValue() {
      var tok = tokens[pos];
      if (tok.type === 'number') { pos++; return { __num: tok.raw }; }
      if (tok.type === 'string') { pos++; return tok.value; }
      if (tok.type === 'true' || tok.type === 'false' || tok.type === 'null') { pos++; return tok.value; }
      if (tok.type === '[') return parseArray();
      if (tok.type === '{') return parseObject();
      throw new Error('Unexpected token ' + tok.type);
    }
    function parseArray() {
      pos++;
      var arr = [];
      if (tokens[pos] && tokens[pos].type === ']') { pos++; return arr; }
      while (true) {
        arr.push(parseValue());
        var tok = tokens[pos++];
        if (tok.type === ',') continue;
        if (tok.type === ']') return arr;
        throw new Error('Expected , or ] got ' + tok.type);
      }
    }
    function parseObject() {
      pos++;
      var obj = {};
      if (tokens[pos] && tokens[pos].type === '}') { pos++; return obj; }
      while (true) {
        var keyTok = tokens[pos++];
        if (keyTok.type !== 'string') throw new Error('Expected string key');
        var key = keyTok.value;
        if (tokens[pos++].type !== ':') throw new Error('Expected :');
        obj[key] = parseValue();
        var tok = tokens[pos++];
        if (tok.type === ',') continue;
        if (tok.type === '}') return obj;
        throw new Error('Expected , or } got ' + tok.type);
      }
    }
    var val = parseValue();
    if (pos !== tokens.length) throw new Error('Unexpected trailing tokens');
    return val;
  }

  // JCS number encoding from raw JSON number text (matches Python rfc8785):
  // integers verbatim, 900.0 -> "900". Raw preservation was a bug.
  function jcsNumberFromRaw(raw) {
    if (/^-?(0|[1-9][0-9]*)$/.test(raw)) return raw;
    var n = Number(raw);
    if (!isFinite(n)) return 'null';
    return String(n);
  }

  // ISO-8601 -> UTC Z form (matches Python serialize.normalize_value):
  // numeric offsets convert, fractions drop, tz-less strings untouched
  // (those were plain strings — a real datetime always carries tz).
  function epiUtcZ(s) {
    if (typeof s !== 'string') return s;
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$/.exec(s);
    if (!m || !m[8]) return s;
    var ms = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
    var off = m[8];
    if (off !== 'Z') {
      var sign = off[0] === '+' ? 1 : -1;
      var parts = off.slice(1).split(':');
      ms -= ((parseInt(parts[0], 10) * 60) + parseInt(parts[1] || '0', 10)) * sign * 60000;
    }
    var d = new Date(ms);
    function p(n) { return (n < 10 ? '0' : '') + n; }
    return d.getUTCFullYear() + '-' + p(d.getUTCMonth() + 1) + '-' + p(d.getUTCDate()) +
      'T' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ':' + p(d.getUTCSeconds()) + 'Z';
  }

  // Era switch: pre-JCS Python signed json.dumps output where 900.0 stays
  // "900.0" (raw preservation correct); JCS era hashes "900". The golden
  // 4.3.0 manifest carries no floats, but correctness must not depend on that.
  var _jcsNumbers = true;

  function sortedJSON(obj) {
    if (obj && typeof obj === 'object' && obj.__num !== undefined) {
      return _jcsNumbers ? jcsNumberFromRaw(obj.__num) : obj.__num;
    }
    if (obj === null) return 'null';
    if (typeof obj === 'string') return JSON.stringify(obj);
    if (typeof obj === 'number') return String(Number.isFinite(obj) ? obj : 'null');
    if (typeof obj === 'boolean') return String(obj);
    if (Array.isArray(obj)) return '[' + obj.map(sortedJSON).join(',') + ']';
    var keys = Object.keys(obj).sort(), p = [];
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (obj[k] !== undefined) p.push(JSON.stringify(k) + ':' + sortedJSON(obj[k]));
    }
    return '{' + p.join(',') + '}';
  }

  function normalizeCreatedAt(manifest) {
    // UTC-convert every tz-carrying datetime string in the manifest.
    (function walk(o) {
      if (!o || typeof o !== 'object' || o.__num !== undefined) return;
      if (Array.isArray(o)) {
        for (var i = 0; i < o.length; i++) {
          if (typeof o[i] === 'string') o[i] = epiUtcZ(o[i]); else walk(o[i]);
        }
        return;
      }
      for (var k in o) {
        if (typeof o[k] === 'string') o[k] = epiUtcZ(o[k]); else walk(o[k]);
      }
    })(manifest);
    return manifest;
  }

  function omitAbsentOptionalHashFields(manifest) {
    if (!manifest || typeof manifest !== 'object') return manifest;
    if (manifest.content_truncated === null || manifest.content_truncated === undefined) {
      delete manifest.content_truncated;
    }
    if (manifest.policy_load_status === null || manifest.policy_load_status === undefined) {
      delete manifest.policy_load_status;
    }
    if (manifest.producer_version === null || manifest.producer_version === undefined) {
      delete manifest.producer_version;
    }
    return manifest;
  }

  function computeManifestHash(rawManifestText) {
    var peek = {};
    try { peek = JSON.parse(rawManifestText); } catch (_e) {}
    var _maj = parseInt(String(peek.spec_version || '').replace(/^v/i, '').split('.')[0], 10);
    if (_maj === 1) {
      throw new Error('Legacy CBOR manifest (v1.x) cannot be verified in the browser — use epi verify on the CLI');
    }
    var legacy = isPreJcsSpec(peek.spec_version);
    _jcsNumbers = !legacy;
    var manifest = legacy ? parseJSONPreserveNumbers(rawManifestText) : peek;
    omitAbsentOptionalHashFields(manifest);
    normalizeCreatedAt(manifest);
    delete manifest.signature;
    return sha256(new TextEncoder().encode(sortedJSON(manifest)));
  }

  function deriveKeyName(pubKeyHex) {
    return sha256(new TextEncoder().encode(pubKeyHex)).then(function (hash) {
      return hash.substring(0, 16);
    });
  }

  function verifyEd25519(sigStr, pubKeyHex, hashHex) {
    return (async function () {
      try {
        var parts = String(sigStr).split(':');
        if (parts.length !== 3 || parts[0] !== 'ed25519') {
          return { valid: false, msg: 'Unsupported signature' };
        }
        var rawSigHex = parts[2];
        var sigBytes = new Uint8Array(rawSigHex.match(/.{1,2}/g).map(function (b) { return parseInt(b, 16); }));
        var pubBytes = new Uint8Array(pubKeyHex.match(/.{1,2}/g).map(function (b) { return parseInt(b, 16); }));
        if (pubBytes.length !== 32) return { valid: false, msg: 'Invalid public key length' };
        var expectedKeyName = await deriveKeyName(pubKeyHex);
        if (parts[1] !== expectedKeyName) return { valid: false, msg: 'Key name does not match public key' };
        var hashBytes = new Uint8Array(hashHex.match(/.{1,2}/g).map(function (b) { return parseInt(b, 16); }));
        var key = await crypto.subtle.importKey('raw', pubBytes, { name: 'Ed25519' }, false, ['verify']);
        var ok = await crypto.subtle.verify({ name: 'Ed25519' }, key, sigBytes, hashBytes);
        return { valid: ok, msg: ok ? 'Signature valid' : 'Signature invalid' };
      } catch (e) {
        return { valid: null, msg: 'Ed25519 error: ' + e.message };
      }
    })();
  }

  global.epiIsPreJcsSpec = isPreJcsSpec;
  global.epiComputeManifestHash = computeManifestHash;
  global.epiVerifyEd25519 = verifyEd25519;
  global.epiParseJSONPreserveNumbers = parseJSONPreserveNumbers;
  global.epiSortedJSON = sortedJSON;
})(typeof window !== 'undefined' ? window : globalThis);
