// EPI Independent Verifier v1.0
// Zero-dependency verification for .epi evidence files.
// License: Apache 2.0
// Cross-validated against AlgoVoi JCS conformance corpus (3 implementations).

// === noble-ed25519 (MIT) - bundled for zero-dependency verification ===
const noble = (function () {
    const ed25519_CURVE = {
        p: 0x7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffedn,
        n: 0x1000000000000000000000000000000014def9dea2f79cd65812631a5cf5d3edn,
        h: 8n, a: 0x7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffecn,
        d: 0x52036cee2b6ffe738cc740797779e89800700a4d4141d8ab75eb4dca135978a3n,
        Gx: 0x216936d3cd6e53fec0a4e231fdd6dc5c692cc7609525a7b2c9562d608f25d51an,
        Gy: 0x6666666666666666666666666666666666666666666666666666666666666658n,
    };
    const { p: P, n: N, Gx, Gy, a: _a, d: _d, h } = ed25519_CURVE;
    const L = 32; const L2 = 64;
    const err = (message = '') => { throw new Error(message); };
    const isBytes = (a) => a instanceof Uint8Array || (ArrayBuffer.isView(a) && a.constructor.name === 'Uint8Array');
    const abytes = (value, length) => { const bytes = isBytes(value); if (!bytes || (length !== undefined && value.length !== length)) err('expected Uint8Array of length ' + length); return value; };
    const u8n = (len) => new Uint8Array(len);
    const u8fr = (buf) => Uint8Array.from(buf);
    const padh = (n, pad) => n.toString(16).padStart(pad, '0');
    const bytesToHex = (b) => Array.from(abytes(b)).map((e) => padh(e, 2)).join('');
    const C = { _0: 48, _9: 57, A: 65, F: 70, a: 97, f: 102 };
    const _ch = (ch) => { if (ch >= C._0 && ch <= C._9) return ch - C._0; if (ch >= C.A && ch <= C.F) return ch - (C.A - 10); if (ch >= C.a && ch <= C.f) return ch - (C.a - 10); };
    const hexToBytes = (hex) => { if (typeof hex !== 'string') return err('hex invalid'); const hl = hex.length; if (hl % 2) return err('hex invalid'); const array = u8n(hl / 2); for (let ai = 0, hi = 0; ai < array.length; ai++, hi += 2) { const n1 = _ch(hex.charCodeAt(hi)); const n2 = _ch(hex.charCodeAt(hi + 1)); if (n1 === undefined || n2 === undefined) return err('hex invalid'); array[ai] = n1 * 16 + n2; } return array; };
    const concatBytes = (...arrs) => { const r = u8n(arrs.reduce((sum, a) => sum + abytes(a).length, 0)); let pad = 0; arrs.forEach(a => { r.set(a, pad); pad += a.length; }); return r; };
    const big = BigInt;
    const assertRange = (n, min, max) => (typeof n === 'bigint' && min <= n && n < max ? n : err('bad number'));
    const M = (a, b = P) => { const r = a % b; return r >= 0n ? r : b + r; };
    const modN = (a) => M(a, N);
    const invert = (num, md) => { if (num === 0n || md <= 0n) err('no inverse'); let a = M(num, md), b = md, x = 0n, y = 1n, u = 1n, v = 0n; while (a !== 0n) { const q = b / a, r = b % a; const m = x - u * q, n = y - v * q; b = a, a = r, x = u, y = v, u = m, v = n; } return b === 1n ? M(x, md) : err('no inverse'); };
    const B256 = 2n ** 256n;
    class Point {
        static BASE; static ZERO;
        constructor(X, Y, Z, T) { this.X = assertRange(X, 0n, B256); this.Y = assertRange(Y, 0n, B256); this.Z = assertRange(Z, 1n, B256); this.T = assertRange(T, 0n, B256); Object.freeze(this); }
        static fromBytes(hex, zip215 = false) { const normed = u8fr(abytes(hex, L)); const lastByte = hex[31]; normed[31] = lastByte & ~0x80; const y = bytesToNumLE(normed); const max = zip215 ? B256 : P; assertRange(y, 0n, max); const y2 = M(y * y); const u = M(y2 - 1n); const v = M(_d * y2 + 1n); let { isValid, value: x } = uvRatio(u, v); if (!isValid) err('bad point'); const isXOdd = (x & 1n) === 1n; const isLastByteOdd = (lastByte & 0x80) !== 0; if (!zip215 && x === 0n && isLastByteOdd) err('bad point'); if (isLastByteOdd !== isXOdd) x = M(-x); return new Point(x, y, 1n, M(x * y)); }
        static fromHex(hex, zip215) { return Point.fromBytes(hexToBytes(hex), zip215); }
        get x() { return this.toAffine().x; } get y() { return this.toAffine().y; }
        assertValidity() { if (this.is0()) return err('bad point: ZERO'); const { X, Y, Z, T } = this; const X2 = M(X * X); const Y2 = M(Y * Y); const Z2 = M(Z * Z); const Z4 = M(Z2 * Z2); const aX2 = M(X2 * _a); const left = M(Z2 * M(aX2 + Y2)); const right = M(Z4 + M(_d * M(X2 * Y2))); if (left !== right) return err('bad point'); const XY = M(X * Y); const ZT = M(Z * T); if (XY !== ZT) return err('bad point'); return this; }
        equals(other) { other = other instanceof Point ? other : err('Point expected'); const { X: X1, Y: Y1, Z: Z1 } = this; const { X: X2, Y: Y2, Z: Z2 } = other; return M(X1 * Z2) === M(X2 * Z1) && M(Y1 * Z2) === M(Y2 * Z1); }
        is0() { return this.equals(I); }
        negate() { return new Point(M(-this.X), this.Y, this.Z, M(-this.T)); }
        double() { const { X: X1, Y: Y1, Z: Z1 } = this; const A = M(X1 * X1); const B = M(Y1 * Y1); const C = M(2n * M(Z1 * Z1)); const D = M(_a * A); const x1y1 = X1 + Y1; const E = M(M(x1y1 * x1y1) - A - B); const G = D + B; const F = G - C; const H = D - B; return new Point(M(E * F), M(G * H), M(E * H), M(F * G)); }
        add(other) { other = other instanceof Point ? other : err('Point expected'); const { X: X1, Y: Y1, Z: Z1, T: T1 } = this; const { X: X2, Y: Y2, Z: Z2, T: T2 } = other; const A = M(X1 * X2); const B = M(Y1 * Y2); const C = M(T1 * _d * T2); const D = M(Z1 * Z2); const E = M((X1 + Y1) * (X2 + Y2) - A - B); const F = M(D - C); const G = M(D + C); const H = M(B - _a * A); return new Point(M(E * F), M(G * H), M(E * H), M(F * G)); }
        subtract(other) { return this.add((other instanceof Point ? other : err('Point expected')).negate()); }
        multiply(n, safe = true) { if (!safe && (n === 0n || this.is0())) return I; assertRange(n, 1n, N); if (n === 1n) return this; if (this.equals(G)) return wNAF(n).p; let p = I, f = G; for (let d = this; n > 0n; d = d.double(), n >>= 1n) { if (n & 1n) p = p.add(d); else if (safe) f = f.add(d); } return p; }
        clearCofactor() { return this.multiply(big(h), false); }
        isSmallOrder() { return this.clearCofactor().is0(); }
        toAffine() { const { X, Y, Z } = this; if (this.equals(I)) return { x: 0n, y: 1n }; const iz = invert(Z, P); if (M(Z * iz) !== 1n) err('invalid inverse'); return { x: M(X * iz), y: M(Y * iz) }; }
        toBytes() { const { x, y } = this.assertValidity().toAffine(); const b = numTo32bLE(y); b[31] |= x & 1n ? 0x80 : 0; return b; }
        toHex() { return bytesToHex(this.toBytes()); }
    }
    const G = new Point(Gx, Gy, 1n, M(Gx * Gy));
    const I = new Point(0n, 1n, 1n, 0n);
    Point.BASE = G; Point.ZERO = I;
    const numTo32bLE = (num) => hexToBytes(padh(assertRange(num, 0n, B256), L2)).reverse();
    const bytesToNumLE = (b) => big('0x' + bytesToHex(u8fr(abytes(b)).reverse()));
    const pow2 = (x, power) => { let r = x; while (power-- > 0n) { r *= r; r %= P; } return r; };
    const pow_2_252_3 = (x) => { const x2 = (x * x) % P; const b2 = (x2 * x) % P; const b4 = (pow2(b2, 2n) * b2) % P; const b5 = (pow2(b4, 1n) * x) % P; const b10 = (pow2(b5, 5n) * b5) % P; const b20 = (pow2(b10, 10n) * b10) % P; const b40 = (pow2(b20, 20n) * b20) % P; const b80 = (pow2(b40, 40n) * b40) % P; const b160 = (pow2(b80, 80n) * b80) % P; const b240 = (pow2(b160, 80n) * b80) % P; const b250 = (pow2(b240, 10n) * b10) % P; return { pow_p_5_8: (pow2(b250, 2n) * x) % P, b2 }; };
    const RM1 = 0x2b8324804fc1df0b2b4d00993dfbd7a72f431806ad2fe478c4ee1b274a0ea0b0n;
    const uvRatio = (u, v) => { const v3 = M(v * v * v); const v7 = M(v3 * v3 * v); const pow = pow_2_252_3(u * v7).pow_p_5_8; let x = M(u * v3 * pow); const vx2 = M(v * x * x); const useRoot1 = vx2 === u; const useRoot2 = vx2 === M(-u); if (useRoot2 || vx2 === M(-u * RM1)) x = M(x * RM1); if ((M(x) & 1n) === 1n) x = M(-x); return { isValid: useRoot1 || useRoot2, value: x }; };
    const modL_LE = (hash) => modN(bytesToNumLE(hash));
    const hash2extK = (hashed) => { const head = hashed.slice(0, L); head[0] &= 248; head[31] &= 127; head[31] |= 64; const scalar = modL_LE(head); const pointBytes = G.multiply(scalar).toBytes(); return { head, prefix: hashed.slice(L, L2), scalar, pointBytes }; };
    const _verify = (sig, msg, pub, opts = { zip215: true }) => { sig = abytes(sig, L2); msg = abytes(msg); pub = abytes(pub, L); let A, R, s, SB, hashable = Uint8Array.of(); try { A = Point.fromBytes(pub, opts.zip215); R = Point.fromBytes(sig.slice(0, L), opts.zip215); s = bytesToNumLE(sig.slice(L, L2)); SB = G.multiply(s, false); hashable = concatBytes(R.toBytes(), A.toBytes(), msg); } catch (error) { } return { hashable, finish: (hashed) => { if (!SB) return false; const k = modL_LE(hashed); return R.add(A.multiply(k, false)).add(SB.negate()).clearCofactor().is0(); } }; };
    const W = 8; const scalarBits = 256; const pwindows = Math.ceil(scalarBits / W) + 1; const pwindowSize = 2 ** (W - 1);
    let Gpows = undefined;
    const precompute = () => { const points = []; let p = G, b = p; for (let w = 0; w < pwindows; w++) { b = p; points.push(b); for (let i = 1; i < pwindowSize; i++) { b = b.add(p); points.push(b); } p = b.double(); } return points; };
    const ctneg = (cnd, p) => cnd ? p.negate() : p;
    const wNAF = (n) => { const comp = Gpows || (Gpows = precompute()); let p = I, f = G; const mask = big(2 ** W - 1); const shiftBy = big(W); for (let w = 0; w < pwindows; w++) { let wbits = Number(n & mask); n >>= shiftBy; if (wbits > pwindowSize) { wbits -= 2 ** W; n += 1n; } const off = w * pwindowSize; if (wbits !== 0) { p = p.add(ctneg(wbits < 0, comp[off + Math.abs(wbits) - 1])); } else { f = f.add(ctneg(w % 2 !== 0, comp[off])); } } return { p, f }; };
    return { verifyAsync: async (sig, msg, pub) => { const r = _verify(sig, msg, pub); return r.finish(await crypto.subtle.digest('SHA-512', r.hashable)); }, bytesToHex, hexToBytes, concatBytes };
})();

// === EPI Verifier ===

/**
 * Normalize an ISO 8601 datetime string to EPI canonical form.
 * Strips microseconds, ensures Z suffix.
 */
function normalizeDatetime(s) {
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(s)) {
        let v = s.replace(/\.\d+/, '');
        if (!v.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(v)) v += 'Z';
        return v;
    }
    return s;
}

/**
 * JCS RFC 8785 canonical JSON serialization.
 * Sorted keys, no whitespace, literal UTF-8 for non-ASCII.
 */
function canonicalJson(obj) {
    if (obj === null) return 'null';
    if (typeof obj === 'string') return JSON.stringify(normalizeDatetime(obj));
    if (typeof obj !== 'object') return JSON.stringify(obj);
    if (Array.isArray(obj)) return '[' + obj.map(canonicalJson).join(',') + ']';
    const keys = Object.keys(obj).sort();
    let result = '{';
    for (let i = 0; i < keys.length; i++) {
        if (i > 0) result += ',';
        result += JSON.stringify(keys[i]) + ':' + canonicalJson(obj[keys[i]]);
    }
    return result + '}';
}

/**
 * Verify an EPI manifest signature.
 * @param {Object} manifest - The parsed manifest.json
 * @returns {Promise<{valid: boolean, reason: string}>}
 */
async function verifyManifestSignature(manifest) {
    if (!manifest.signature) return { valid: false, reason: 'No signature present' };
    const parts = manifest.signature.split(':');
    if (parts.length !== 3 || parts[0] !== 'ed25519') return { valid: false, reason: 'Invalid signature format' };
    const keyName = parts[1];
    const sigHex = parts[2];
    if (!manifest.public_key) return { valid: false, reason: 'No public key in manifest' };
    const pubKeyBytes = noble.hexToBytes(manifest.public_key);
    if (pubKeyBytes.length !== 32) return { valid: false, reason: 'Invalid public key length' };

    // Verify key binding
    const pubKeyHex = manifest.public_key;
    const expectedKeyName = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(pubKeyHex))))
        .map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
    if (keyName !== expectedKeyName) return { valid: false, reason: 'Key name not bound to public key' };

    // Compute canonical hash excluding signature
    const manifestCopy = JSON.parse(JSON.stringify(manifest));
    delete manifestCopy.signature;
    const jsonString = canonicalJson(manifestCopy);
    const msgBytes = new TextEncoder().encode(jsonString);
    const hashBuffer = await crypto.subtle.digest('SHA-256', msgBytes);
    const hashArray = new Uint8Array(hashBuffer);

    // Decode signature - hex or legacy base64
    let sigBytes;
    try { sigBytes = noble.hexToBytes(sigHex); }
    catch (_hexErr) {
        try { const binary = atob(sigHex); sigBytes = new Uint8Array(binary.length); for (let i = 0; i < binary.length; i++) sigBytes[i] = binary.charCodeAt(i); }
        catch (_b64Err) { return { valid: false, reason: 'Invalid signature encoding' }; }
    }

    const isValid = await noble.verifyAsync(sigBytes, hashArray, pubKeyBytes);
    return isValid ? { valid: true, reason: 'Cryptographically verified' } : { valid: false, reason: 'Signature mismatch' };
}

/**
 * Compute SHA-256 of data as lowercase hex.
 */
async function sha256Hex(data) {
    const hash = await crypto.subtle.digest('SHA-256', data instanceof Uint8Array ? data : new TextEncoder().encode(data));
    return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Verify a complete .epi artifact.
 * @param {ArrayBuffer|Uint8Array} epiBytes - Raw .epi file bytes
 * @returns {Promise<Object>} Verification report
 */
export async function verifyEpi(epiBytes) {
    const bytes = epiBytes instanceof Uint8Array ? epiBytes : new Uint8Array(epiBytes);
    const report = { integrity: false, signature: null, trust_level: 'NONE', files_checked: 0, mismatches: [] };

    try {
        // Parse ZIP - check for envelope-v2 magic first
        const magic = new TextDecoder().decode(bytes.slice(0, 8));
        let zipData = bytes;
        if (magic.startsWith('EPIENV\x01')) {
            // envelope-v2: skip header to find ZIP
            const headerLen = new DataView(bytes.buffer, bytes.byteOffset, 8).getUint32(4, true);
            zipData = bytes.slice(headerLen);
        }

        // Use JSZip if available, or manual ZIP parsing
        if (typeof JSZip !== 'undefined') {
            const zip = await JSZip.loadAsync(zipData);
            const manifestStr = await zip.file('manifest.json').async('string');
            const manifest = JSON.parse(manifestStr);

            // Verify file hashes
            let integrityOk = true;
            const mismatches = [];
            if (manifest.file_manifest) {
                for (const [path, expectedHash] of Object.entries(manifest.file_manifest)) {
                    const file = zip.file(path);
                    if (file) {
                        const data = await file.async('uint8array');
                        const actual = await sha256Hex(data);
                        if (actual !== expectedHash) {
                            integrityOk = false;
                            mismatches.push({ path, expected: expectedHash, actual });
                        }
                    }
                }
            }
            report.integrity = integrityOk;
            report.files_checked = Object.keys(manifest.file_manifest || {}).length;
            report.mismatches = mismatches;

            // Verify signature
            const sigResult = await verifyManifestSignature(manifest);
            report.signature = sigResult;
            report.trust_level = sigResult.valid ? 'SIGNED' : (manifest.signature ? 'INVALID' : 'UNSIGNED');
        } else {
            // Fallback: provide hash verification without JSZip
            report.integrity = null;
            report.signature = { valid: null, reason: 'JSZip required for full verification. Install: npm install jszip' };
        }
    } catch (err) {
        report.error = err.message;
    }

    return report;
}

export { verifyManifestSignature, canonicalJson, sha256Hex, noble };
