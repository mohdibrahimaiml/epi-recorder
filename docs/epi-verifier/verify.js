// EPI Independent Verifier v1.0
// Zero-dependency verification for .epi evidence files.
// License: MIT (same as the epi-recorder repository)
// Cross-validated against AlgoVoi JCS conformance corpus (3 implementations).

// === noble-ed25519 (MIT) - bundled for zero-dependency verification ===
const noble = (function () {
    const ed25519_CURVE = {
        p: 0x7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffedn,
        n: 0x1000000000000000000000000000000014def9dea2f79cd65812631a5cf5d3edn,
        h: 8n,
        a: 0x7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffecn,
        d: 0x52036cee2b6ffe738cc740797779e89800700a4d4141d8ab75eb4dca135978a3n,
        Gx: 0x216936d3cd6e53fec0a4e231fdd6dc5c692cc7609525a7b2c9562d608f25d51an,
        Gy: 0x6666666666666666666666666666666666666666666666666666666666666658n,
    };
    const { p: P, n: N, Gx, Gy, a: _a, d: _d, h } = ed25519_CURVE;
    const L = 32;
    const L2 = 64;

    const captureTrace = (...args) => {
        if ('captureStackTrace' in Error && typeof Error.captureStackTrace === 'function') {
            Error.captureStackTrace(...args);
        }
    };
    const err = (message = '') => {
        const e = new Error(message);
        captureTrace(e, err);
        throw e;
    };
    const isBig = (n) => typeof n === 'bigint';
    const isStr = (s) => typeof s === 'string';
    const isBytes = (a) => a instanceof Uint8Array || (ArrayBuffer.isView(a) && a.constructor.name === 'Uint8Array');
    const abytes = (value, length, title = '') => {
        const bytes = isBytes(value);
        const len = value?.length;
        const needsLen = length !== undefined;
        if (!bytes || (needsLen && len !== length)) {
            const prefix = title && `"${title}" `;
            const ofLen = needsLen ? ` of length ${length}` : '';
            const got = bytes ? `length=${len}` : `type=${typeof value}`;
            err(prefix + 'expected Uint8Array' + ofLen + ', got ' + got);
        }
        return value;
    };
    const u8n = (len) => new Uint8Array(len);
    const u8fr = (buf) => Uint8Array.from(buf);
    const padh = (n, pad) => n.toString(16).padStart(pad, '0');
    const bytesToHex = (b) => Array.from(abytes(b))
        .map((e) => padh(e, 2))
        .join('');
    const C = { _0: 48, _9: 57, A: 65, F: 70, a: 97, f: 102 };
    const _ch = (ch) => {
        if (ch >= C._0 && ch <= C._9) return ch - C._0;
        if (ch >= C.A && ch <= C.F) return ch - (C.A - 10);
        if (ch >= C.a && ch <= C.f) return ch - (C.a - 10);
        return;
    };
    const hexToBytes = (hex) => {
        const e = 'hex invalid';
        if (!isStr(hex)) return err(e);
        const hl = hex.length;
        const al = hl / 2;
        if (hl % 2) return err(e);
        const array = u8n(al);
        for (let ai = 0, hi = 0; ai < al; ai++, hi += 2) {
            const n1 = _ch(hex.charCodeAt(hi));
            const n2 = _ch(hex.charCodeAt(hi + 1));
            if (n1 === undefined || n2 === undefined) return err(e);
            array[ai] = n1 * 16 + n2;
        }
        return array;
    };
    const cr = () => globalThis?.crypto;
    const subtle = () => cr()?.subtle ?? err('crypto.subtle must be defined, consider polyfill');

    const concatBytes = (...arrs) => {
        const r = u8n(arrs.reduce((sum, a) => sum + abytes(a).length, 0));
        let pad = 0;
        arrs.forEach(a => { r.set(a, pad); pad += a.length; });
        return r;
    };

    const randomBytes = (len = L) => {
        const c = cr();
        return c.getRandomValues(u8n(len));
    };
    const big = BigInt;
    const assertRange = (n, min, max, msg = 'bad number: out of range') => (isBig(n) && min <= n && n < max ? n : err(msg));
    const M = (a, b = P) => {
        const r = a % b;
        return r >= 0n ? r : b + r;
    };
    const modN = (a) => M(a, N);

    const invert = (num, md) => {
        if (num === 0n || md <= 0n) err('no inverse n=' + num + ' mod=' + md);
        let a = M(num, md), b = md, x = 0n, y = 1n, u = 1n, v = 0n;
        while (a !== 0n) {
            const q = b / a, r = b % a;
            const m = x - u * q, n = y - v * q;
            b = a, a = r, x = u, y = v, u = m, v = n;
        }
        return b === 1n ? M(x, md) : err('no inverse');
    };

    const B256 = 2n ** 256n;

    class Point {
        static BASE;
        static ZERO;
        X; Y; Z; T;
        constructor(X, Y, Z, T) {
            const max = B256;
            this.X = assertRange(X, 0n, max);
            this.Y = assertRange(Y, 0n, max);
            this.Z = assertRange(Z, 1n, max);
            this.T = assertRange(T, 0n, max);
            Object.freeze(this);
        }
        static CURVE() { return ed25519_CURVE; }

        static fromAffine(p) { return new Point(p.x, p.y, 1n, M(p.x * p.y)); }

        static fromBytes(hex, zip215 = false) {
            const d = _d;
            const normed = u8fr(abytes(hex, L));
            const lastByte = hex[31];
            normed[31] = lastByte & ~0x80;
            const y = bytesToNumLE(normed);
            const max = zip215 ? B256 : P;
            assertRange(y, 0n, max);
            const y2 = M(y * y);
            const u = M(y2 - 1n);
            const v = M(d * y2 + 1n);
            let { isValid, value: x } = uvRatio(u, v);
            if (!isValid) err('bad point: y not sqrt');
            const isXOdd = (x & 1n) === 1n;
            const isLastByteOdd = (lastByte & 0x80) !== 0;
            if (!zip215 && x === 0n && isLastByteOdd) err('bad point: x==0, isLastByteOdd');
            if (isLastByteOdd !== isXOdd) x = M(-x);
            return new Point(x, y, 1n, M(x * y));
        }
        static fromHex(hex, zip215) { return Point.fromBytes(hexToBytes(hex), zip215); }
        get x() { return this.toAffine().x; }
        get y() { return this.toAffine().y; }

        assertValidity() {
            const a = _a;
            const d = _d;
            const p = this;
            if (p.is0()) return err('bad point: ZERO');
            const { X, Y, Z, T } = p;
            const X2 = M(X * X);
            const Y2 = M(Y * Y);
            const Z2 = M(Z * Z);
            const Z4 = M(Z2 * Z2);
            const aX2 = M(X2 * a);
            const left = M(Z2 * M(aX2 + Y2));
            const right = M(Z4 + M(d * M(X2 * Y2)));
            if (left !== right) return err('bad point: equation left != right (1)');
            const XY = M(X * Y);
            const ZT = M(Z * T);
            if (XY !== ZT) return err('bad point: equation left != right (2)');
            return this;
        }

        equals(other) {
            const { X: X1, Y: Y1, Z: Z1 } = this;
            const { X: X2, Y: Y2, Z: Z2 } = apoint(other);
            const X1Z2 = M(X1 * Z2);
            const X2Z1 = M(X2 * Z1);
            const Y1Z2 = M(Y1 * Z2);
            const Y2Z1 = M(Y2 * Z1);
            return X1Z2 === X2Z1 && Y1Z2 === Y2Z1;
        }
        is0() { return this.equals(I); }
        negate() { return new Point(M(-this.X), this.Y, this.Z, M(-this.T)); }

        double() {
            const { X: X1, Y: Y1, Z: Z1 } = this;
            const a = _a;
            const A = M(X1 * X1);
            const B = M(Y1 * Y1);
            const C = M(2n * M(Z1 * Z1));
            const D = M(a * A);
            const x1y1 = X1 + Y1;
            const E = M(M(x1y1 * x1y1) - A - B);
            const G = D + B;
            const F = G - C;
            const H = D - B;
            const X3 = M(E * F);
            const Y3 = M(G * H);
            const T3 = M(E * H);
            const Z3 = M(F * G);
            return new Point(X3, Y3, Z3, T3);
        }

        add(other) {
            const { X: X1, Y: Y1, Z: Z1, T: T1 } = this;
            const { X: X2, Y: Y2, Z: Z2, T: T2 } = apoint(other);
            const a = _a;
            const d = _d;
            const A = M(X1 * X2);
            const B = M(Y1 * Y2);
            const C = M(T1 * d * T2);
            const D = M(Z1 * Z2);
            const E = M((X1 + Y1) * (X2 + Y2) - A - B);
            const F = M(D - C);
            const G = M(D + C);
            const H = M(B - a * A);
            const X3 = M(E * F);
            const Y3 = M(G * H);
            const T3 = M(E * H);
            const Z3 = M(F * G);
            return new Point(X3, Y3, Z3, T3);
        }
        subtract(other) { return this.add(apoint(other).negate()); }

        multiply(n, safe = true) {
            if (!safe && (n === 0n || this.is0())) return I;
            assertRange(n, 1n, N);
            if (n === 1n) return this;
            if (this.equals(G)) return wNAF(n).p;
            let p = I;
            let f = G;
            for (let d = this; n > 0n; d = d.double(), n >>= 1n) {
                if (n & 1n) p = p.add(d);
                else if (safe) f = f.add(d);
            }
            return p;
        }
        multiplyUnsafe(scalar) { return this.multiply(scalar, false); }

        toAffine() {
            const { X, Y, Z } = this;
            if (this.equals(I)) return { x: 0n, y: 1n };
            const iz = invert(Z, P);
            if (M(Z * iz) !== 1n) err('invalid inverse');
            const x = M(X * iz);
            const y = M(Y * iz);
            return { x, y };
        }
        toBytes() {
            const { x, y } = this.assertValidity().toAffine();
            const b = numTo32bLE(y);
            b[31] |= x & 1n ? 0x80 : 0;
            return b;
        }
        toHex() { return bytesToHex(this.toBytes()); }
        clearCofactor() { return this.multiply(big(h), false); }
        isSmallOrder() { return this.clearCofactor().is0(); }
        isTorsionFree() {
            let p = this.multiply(N / 2n, false).double();
            if (N % 2n) p = p.add(this);
            return p.is0();
        }
    }

    const G = new Point(Gx, Gy, 1n, M(Gx * Gy));
    const I = new Point(0n, 1n, 1n, 0n);
    Point.BASE = G;
    Point.ZERO = I;

    const numTo32bLE = (num) => hexToBytes(padh(assertRange(num, 0n, B256), L2)).reverse();
    const bytesToNumLE = (b) => big('0x' + bytesToHex(u8fr(abytes(b)).reverse()));

    const pow2 = (x, power) => {
        let r = x;
        while (power-- > 0n) { r *= r; r %= P; }
        return r;
    };

    const pow_2_252_3 = (x) => {
        const x2 = (x * x) % P;
        const b2 = (x2 * x) % P;
        const b4 = (pow2(b2, 2n) * b2) % P;
        const b5 = (pow2(b4, 1n) * x) % P;
        const b10 = (pow2(b5, 5n) * b5) % P;
        const b20 = (pow2(b10, 10n) * b10) % P;
        const b40 = (pow2(b20, 20n) * b20) % P;
        const b80 = (pow2(b40, 40n) * b40) % P;
        const b160 = (pow2(b80, 80n) * b80) % P;
        const b240 = (pow2(b160, 80n) * b80) % P;
        const b250 = (pow2(b240, 10n) * b10) % P;
        const pow_p_5_8 = (pow2(b250, 2n) * x) % P;
        return { pow_p_5_8, b2 };
    };

    const RM1 = 0x2b8324804fc1df0b2b4d00993dfbd7a72f431806ad2fe478c4ee1b274a0ea0b0n;

    const uvRatio = (u, v) => {
        const v3 = M(v * v * v);
        const v7 = M(v3 * v3 * v);
        const pow = pow_2_252_3(u * v7).pow_p_5_8;
        let x = M(u * v3 * pow);
        const vx2 = M(v * x * x);
        const root1 = x;
        const root2 = M(x * RM1);
        const useRoot1 = vx2 === u;
        const useRoot2 = vx2 === M(-u);
        const noRoot = vx2 === M(-u * RM1);
        if (useRoot1) x = root1;
        if (useRoot2 || noRoot) x = root2;
        if ((M(x) & 1n) === 1n) x = M(-x);
        return { isValid: useRoot1 || useRoot2, value: x };
    };

    const modL_LE = (hash) => modN(bytesToNumLE(hash));

    const callHash = (name) => {
        const fn = hashes[name];
        if (typeof fn !== 'function') err('hashes.' + name + ' not set');
        return fn;
    };
    const sha512a = (...m) => hashes.sha512Async(concatBytes(...m));
    const sha512s = (...m) => callHash('sha512')(concatBytes(...m));

    const hash2extK = (hashed) => {
        const head = hashed.slice(0, L);
        head[0] &= 248;
        head[31] &= 127;
        head[31] |= 64;
        const prefix = hashed.slice(L, L2);
        const scalar = modL_LE(head);
        const point = G.multiply(scalar);
        const pointBytes = point.toBytes();
        return { head, prefix, scalar, point, pointBytes };
    };

    const apoint = (p) => (p instanceof Point ? p : err('Point expected'));

    const getExtendedPublicKeyAsync = (secretKey) => sha512a(abytes(secretKey, L)).then(hash2extK);
    const getExtendedPublicKey = (secretKey) => hash2extK(sha512s(abytes(secretKey, L)));
    const getPublicKeyAsync = (secretKey) => getExtendedPublicKeyAsync(secretKey).then((p) => p.pointBytes);
    const getPublicKey = (priv) => getExtendedPublicKey(priv).pointBytes;

    const hashFinishA = (res) => sha512a(res.hashable).then(res.finish);
    const hashFinishS = (res) => res.finish(sha512s(res.hashable));

    const defaultVerifyOpts = { zip215: true };
    const _verify = (sig, msg, pub, opts = defaultVerifyOpts) => {
        sig = abytes(sig, L2);
        msg = abytes(msg);
        pub = abytes(pub, L);
        const { zip215 } = opts;
        let A; let R; let s; let SB;
        let hashable = Uint8Array.of();
        try {
            A = Point.fromBytes(pub, zip215);
            R = Point.fromBytes(sig.slice(0, L), zip215);
            s = bytesToNumLE(sig.slice(L, L2));
            SB = G.multiply(s, false);
            hashable = concatBytes(R.toBytes(), A.toBytes(), msg);
        }
        catch (error) { }
        const finish = (hashed) => {
            if (SB == null) return false;
            if (!zip215 && A.isSmallOrder()) return false;
            const k = modL_LE(hashed);
            const RkA = R.add(A.multiply(k, false));
            return RkA.add(SB.negate()).clearCofactor().is0();
        };
        return { hashable, finish };
    };

    const verifyAsync = async (signature, message, publicKey, opts = defaultVerifyOpts) => hashFinishA(_verify(signature, message, publicKey, opts));

    // Ed25519 sign (message bytes → 64-byte signature). Used by browser Sign & Seal.
    const signAsync = async (message, secretKey) => {
        const { prefix, scalar, pointBytes } = await getExtendedPublicKeyAsync(secretKey);
        const r = modL_LE(await sha512a(prefix, message));
        const R = G.multiply(r).toBytes();
        const k = modL_LE(await sha512a(R, pointBytes, message));
        const s = modN(r + k * scalar);
        return concatBytes(R, numTo32bLE(s));
    };

    const etc = {
        bytesToHex: bytesToHex,
        hexToBytes: hexToBytes,
        concatBytes: concatBytes,
        mod: M,
        invert: invert,
        randomBytes: randomBytes,
    };

    const hashes = {
        sha512Async: async (message) => {
            const s = subtle();
            const m = concatBytes(message);
            return u8n(await s.digest('SHA-512', m.buffer));
        },
        sha512: undefined,
    };

    const W = 8;
    const scalarBits = 256;
    const pwindows = Math.ceil(scalarBits / W) + 1;
    const pwindowSize = 2 ** (W - 1);
    const precompute = () => {
        const points = [];
        let p = G;
        let b = p;
        for (let w = 0; w < pwindows; w++) {
            b = p;
            points.push(b);
            for (let i = 1; i < pwindowSize; i++) {
                b = b.add(p);
                points.push(b);
            }
            p = b.double();
        }
        return points;
    };
    let Gpows = undefined;
    const ctneg = (cnd, p) => {
        const n = p.negate();
        return cnd ? n : p;
    };
    const wNAF = (n) => {
        const comp = Gpows || (Gpows = precompute());
        let p = I;
        let f = G;
        const pow_2_w = 2 ** W;
        const maxNum = pow_2_w;
        const mask = big(pow_2_w - 1);
        const shiftBy = big(W);
        for (let w = 0; w < pwindows; w++) {
            let wbits = Number(n & mask);
            n >>= shiftBy;
            if (wbits > pwindowSize) {
                wbits -= maxNum;
                n += 1n;
            }
            const off = w * pwindowSize;
            const offF = off;
            const offP = off + Math.abs(wbits) - 1;
            const isEven = w % 2 !== 0;
            const isNeg = wbits < 0;
            if (wbits === 0) {
                f = f.add(ctneg(isEven, comp[offF]));
            }
            else {
                p = p.add(ctneg(isNeg, comp[offP]));
            }
        }
        return { p, f };
    };

    return { verifyAsync, signAsync, getPublicKey, getPublicKeyAsync, etc };
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
    // CBOR-sealed v1.x manifests cannot be verified here (no CBOR
    // canonicalizer in this helper). Fail with directions, not a tamper verdict.
    var _svMaj = parseInt(String((manifest && manifest.spec_version) || '').replace(/^v/i, '').split('.')[0], 10);
    if (_svMaj === 1) {
        return { valid: false, reason: 'Legacy CBOR manifest (v1.x) — verify with epi verify on the CLI' };
    }
    const parts = manifest.signature.split(':');
    if (parts.length !== 3 || parts[0] !== 'ed25519') return { valid: false, reason: 'Invalid signature format' };
    const keyName = parts[1];
    const sigHex = parts[2];
    if (!manifest.public_key) return { valid: false, reason: 'No public key in manifest' };
    const pubKeyBytes = noble.etc.hexToBytes(manifest.public_key);
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
    try { sigBytes = noble.etc.hexToBytes(sigHex); }
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
 * Locate a byte needle in a haystack starting at `from`. -1 when absent.
 */
function findBytes(haystack, needle, from) {
    const start = from || 0;
    outer: for (let i = start; i + needle.length <= haystack.length; i++) {
        for (let j = 0; j < needle.length; j++) {
            if (haystack[i + j] !== needle[j]) continue outer;
        }
        return i;
    }
    return -1;
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
        // Locate the ZIP payload. Real envelope-v2 files start with '<!--'
        // (128-byte header) followed by viewer HTML and the canonical
        // EPI_ZIP_PAYLOAD_START sentinel (newline-wrapped on both sides,
        // matching epi_core/container.py and website/js/epi-verify-core.js).
        const head = new TextDecoder().decode(bytes.slice(0, 4));
        let zipData = bytes;
        if (head === '<!--') {
            const marker = new TextEncoder().encode('\n<!-- EPI_ZIP_PAYLOAD_START -->\n');
            const markerAt = findBytes(bytes, marker, 128);
            if (markerAt >= 0) {
                zipData = bytes.slice(markerAt + marker.length);
            } else {
                // No viewer shell - payload immediately after 128-byte header.
                zipData = bytes.slice(128);
            }
        } else if (!(bytes[0] === 0x50 && bytes[1] === 0x4b)) {
            throw new Error('Not a .epi file: expected <!-- envelope or PK zip');
        }
        // else: legacy-zip - the whole file is the ZIP.

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
