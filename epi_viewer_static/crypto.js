/*! noble-ed25519 - MIT License (c) 2019 Paul Miller (paulmillr.com) */
// Bundled for EPI Viewer

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
globalThis.noble = noble;

// ==========================================
// EPI Viewer Verification Logic
// ==========================================

async function verifyManifestSignature(manifest) {
    console.log("Verifying manifest signature...", manifest);

    // 1. Check if signature exists
    if (!manifest.signature) {
        console.warn("No signature found");
        return { valid: false, reason: "No signature" };
    }

    // 2. Parse signature string "ed25519:<name>:<hex>"
    const parts = manifest.signature.split(':');
    if (parts.length !== 3 || parts[0] !== 'ed25519') {
        console.error("Invalid signature format");
        return { valid: false, reason: "Invalid format" };
    }

    const keyName = parts[1];
    const sigHex = parts[2];

    // 3. Get Public Key
    if (!manifest.public_key) {
        console.warn("Manifest missing public_key field for verification");
        return { valid: false, reason: "Missing Public Key" };
    }

    const pubKeyBytes = noble.etc.hexToBytes(manifest.public_key);

    // 4. Compute Canonical JSON Hash of Manifest (excluding signature)
    const manifestCopy = JSON.parse(JSON.stringify(manifest));
    delete manifestCopy.signature;

    // Normalize datetime strings to match Python's canonical form:
    // strips microseconds and ensures Z suffix (matches epi_core/serialize.py _normalize_value)
    const normalizeDatetime = (s) => {
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(s)) {
            let v = s.replace(/\.\d+/, ''); // strip microseconds
            if (!v.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(v)) v += 'Z';
            return v;
        }
        return s;
    };

    // Recursive canonical JSON stringify (RFC 8785 style, matches Python get_canonical_hash)
    const canonicalJson = (obj) => {
        if (obj === null) return 'null';
        if (typeof obj === 'string') return JSON.stringify(normalizeDatetime(obj));
        if (typeof obj !== 'object') return JSON.stringify(obj);
        if (Array.isArray(obj)) return '[' + obj.map(canonicalJson).join(',') + ']';

        const keys = Object.keys(obj).sort();
        let result = '{';
        for (let i = 0; i < keys.length; i++) {
            const key = keys[i];
            if (i > 0) result += ',';
            result += JSON.stringify(key) + ':' + canonicalJson(obj[key]);
        }
        return result + '}';
    };

    const jsonString = canonicalJson(manifestCopy);
    const msgBytes = new TextEncoder().encode(jsonString);

    try {
        // 5. Verify Hash
        // The backend signs the SHA-256 hash of the content.
        // So we must convert content -> SHA-256 hash -> verify against signature
        const hashBuffer = await crypto.subtle.digest('SHA-256', msgBytes);
        const hashArray = new Uint8Array(hashBuffer);

        // Decode signature — hex (current format) or base64 (legacy format)
        let sigBytes;
        try {
            sigBytes = noble.etc.hexToBytes(sigHex);
        } catch (_hexErr) {
            try {
                const binary = atob(sigHex);
                sigBytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i++) sigBytes[i] = binary.charCodeAt(i);
            } catch (_b64Err) {
                return { valid: false, reason: "Invalid signature encoding (not hex or base64)" };
            }
        }

        const isValid = await noble.verifyAsync(sigBytes, hashArray, pubKeyBytes);

        if (isValid) {
            return { valid: true, reason: "Cryptographically verified, including Public Key integrity" };
        } else {
            return { valid: false, reason: "Signature mismatch" };
        }
    } catch (e) {
        return { valid: false, reason: e.message };
    }
}

// Expose for embedded forensic viewer self-check (web_viewer/app.js)
globalThis.verifyManifestSignature = verifyManifestSignature;

// ==========================================
// EPI Browser Sign & Seal (envelope-v2 + Ed25519)
// ==========================================
// Private keys never leave the browser except as a user-pasted PEM import.
// Default path: device-local seed in localStorage (not embedded in the .epi).

const EPI_ENVELOPE_MAGIC = new Uint8Array([0x3c, 0x21, 0x2d, 0x2d]); // "<!--"
const EPI_ENVELOPE_VERSION = 2;
const EPI_PAYLOAD_FORMAT_ZIP_V1 = 0x01;
const EPI_ENVELOPE_HEADER_SIZE = 128;
const EPI_ZIP_MARKER_STR = '\n<!-- EPI_ZIP_PAYLOAD_START -->\n';
const EPI_LEGACY_MIMETYPE = 'application/vnd.epi+zip';
const EPI_BROWSER_SEED_STORAGE_KEY = 'epi.viewer.signingSeed.v1';

function epiNormalizeDatetimeForCanonical(s) {
    if (typeof s === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(s)) {
        let v = s.replace(/\.\d+/, '');
        if (!v.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(v)) v += 'Z';
        return v;
    }
    return s;
}

function epiCanonicalJson(obj) {
    if (obj === null) return 'null';
    if (typeof obj === 'string') return JSON.stringify(epiNormalizeDatetimeForCanonical(obj));
    if (typeof obj !== 'object') return JSON.stringify(obj);
    if (Array.isArray(obj)) return '[' + obj.map(epiCanonicalJson).join(',') + ']';
    const keys = Object.keys(obj).sort();
    let result = '{';
    for (let i = 0; i < keys.length; i++) {
        if (i > 0) result += ',';
        result += JSON.stringify(keys[i]) + ':' + epiCanonicalJson(obj[keys[i]]);
    }
    return result + '}';
}

async function epiSha256Bytes(data) {
    const buf = data instanceof ArrayBuffer ? data : data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
    return new Uint8Array(await crypto.subtle.digest('SHA-256', buf));
}

async function epiSha256Hex(data) {
    const bytes = await epiSha256Bytes(data);
    return noble.etc.bytesToHex(bytes);
}

function epiWriteU64LE(view, offset, value) {
    const big = typeof value === 'bigint' ? value : BigInt(value);
    view.setUint32(offset, Number(big & 0xffffffffn), true);
    view.setUint32(offset + 4, Number((big >> 32n) & 0xffffffffn), true);
}

function epiUuidToBytes(workflowId) {
    const out = new Uint8Array(16);
    if (!workflowId) return out;
    const hex = String(workflowId).replace(/-/g, '').toLowerCase();
    if (!/^[0-9a-f]{32}$/.test(hex)) return out;
    for (let i = 0; i < 16; i++) {
        out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
    }
    return out;
}

function epiCreatedAtMicros(createdAt) {
    if (!createdAt) return 0;
    const ms = Date.parse(createdAt);
    if (Number.isNaN(ms)) return 0;
    return Math.trunc(ms * 1000);
}

/**
 * Pack the 128-byte envelope-v2 header (matches epi_core/container.py
 * _EPI_ENVELOPE_HEADER_STRUCT = <4sBBHQ16sQ32s56s).
 */
function epiPackEnvelopeHeader({ payloadLength, uuidBytes, createdAtMicros, payloadSha256 }) {
    const buf = new ArrayBuffer(EPI_ENVELOPE_HEADER_SIZE);
    const view = new DataView(buf);
    const u8 = new Uint8Array(buf);
    // Layout matches _EPI_ENVELOPE_HEADER_STRUCT = <4sBBHQ16sQ32s56s
    // offsets: magic0, ver4, fmt5, flags6, len8, uuid16, created32, hash40, pad72
    u8.set(EPI_ENVELOPE_MAGIC, 0);
    view.setUint8(4, EPI_ENVELOPE_VERSION);
    view.setUint8(5, EPI_PAYLOAD_FORMAT_ZIP_V1);
    view.setUint16(6, 0, true);
    epiWriteU64LE(view, 8, payloadLength);
    u8.set(uuidBytes || new Uint8Array(16), 16);
    epiWriteU64LE(view, 32, createdAtMicros || 0);
    u8.set(payloadSha256 || new Uint8Array(32), 40);
    // reserved tail (bytes 72-127) already zero
    return u8;
}

/**
 * Wrap a ZIP payload as envelope-v2 (.epi), optionally with polyglot HTML.
 * payload_sha256 and payload_length cover the ZIP only (same as Python packer).
 */
async function epiWrapEnvelopeV2(zipBytes, manifest, polyglotHtml) {
    const zip = zipBytes instanceof Uint8Array ? zipBytes : new Uint8Array(zipBytes);
    const payloadHash = await epiSha256Bytes(zip);
    const uuidBytes = epiUuidToBytes(manifest && manifest.workflow_id);
    const createdAtMicros = epiCreatedAtMicros(manifest && manifest.created_at);
    const header = epiPackEnvelopeHeader({
        payloadLength: zip.length,
        uuidBytes,
        createdAtMicros,
        payloadSha256: payloadHash,
    });

    const parts = [header];
    if (polyglotHtml) {
        const encoder = new TextEncoder();
        const htmlBytes = encoder.encode(polyglotHtml);
        const marker = encoder.encode(EPI_ZIP_MARKER_STR);
        if (noble.etc.bytesToHex(htmlBytes).includes(noble.etc.bytesToHex(marker))) {
            // Marker substring check on bytes (avoid corrupting extraction)
            const htmlStr = polyglotHtml;
            if (htmlStr.includes(EPI_ZIP_MARKER_STR)) {
                throw new Error('Viewer HTML contains EPI_ZIP_MARKER sentinel; cannot pack polyglot envelope.');
            }
        }
        parts.push(encoder.encode(' -->\n'));
        parts.push(htmlBytes);
        parts.push(marker);
    }
    parts.push(zip);
    return noble.etc.concatBytes(...parts);
}

/**
 * Device-local signing seed. Never written into the .epi artifact.
 * Returns { seed: Uint8Array, source: 'local'|'imported', fingerprint: string }
 */
async function epiResolveSigningSeed(optionalPemText) {
    if (optionalPemText && String(optionalPemText).trim()) {
        const seed = epiExtractEd25519SeedFromPem(String(optionalPemText).trim());
        const pub = await noble.getPublicKeyAsync(seed);
        return {
            seed,
            source: 'imported',
            fingerprint: noble.etc.bytesToHex(pub).slice(0, 16),
            publicKeyHex: noble.etc.bytesToHex(pub),
        };
    }

    let seed = null;
    try {
        const stored = globalThis.localStorage && localStorage.getItem(EPI_BROWSER_SEED_STORAGE_KEY);
        if (stored && /^[0-9a-fA-F]{64}$/.test(stored)) {
            seed = noble.etc.hexToBytes(stored);
        }
    } catch (_e) {
        // file:// or privacy mode — fall through to ephemeral
    }

    if (!seed) {
        seed = noble.etc.randomBytes(32);
        try {
            if (globalThis.localStorage) {
                localStorage.setItem(EPI_BROWSER_SEED_STORAGE_KEY, noble.etc.bytesToHex(seed));
            }
        } catch (_e) {
            // ephemeral for this session only
        }
    }

    const pub = await noble.getPublicKeyAsync(seed);
    return {
        seed,
        source: 'local',
        fingerprint: noble.etc.bytesToHex(pub).slice(0, 16),
        publicKeyHex: noble.etc.bytesToHex(pub),
    };
}

function epiExtractEd25519SeedFromPem(pemText) {
    if (/BEGIN ENCRYPTED PRIVATE KEY/.test(pemText)) {
        throw new Error('Encrypted private keys are not supported in the browser. Use an unencrypted key from `epi keys generate`.');
    }
    const pemMatch = pemText.match(/-----BEGIN PRIVATE KEY-----([\s\S]+?)-----END PRIVATE KEY-----/);
    let pkcs8;
    if (pemMatch) {
        const b64 = pemMatch[1].replace(/\s+/g, '');
        const binary = atob(b64);
        pkcs8 = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) pkcs8[i] = binary.charCodeAt(i);
    } else if (/^[A-Za-z0-9+/=\s]+$/.test(pemText)) {
        const b64 = pemText.replace(/\s+/g, '');
        const binary = atob(b64);
        pkcs8 = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) pkcs8[i] = binary.charCodeAt(i);
    } else {
        throw new Error('Paste an unencrypted Ed25519 PKCS#8 private key (PEM from `epi keys generate`).');
    }
    for (let index = pkcs8.length - 34; index >= 0; index -= 1) {
        if (pkcs8[index] === 0x04 && pkcs8[index + 1] === 0x20) {
            return pkcs8.slice(index + 2, index + 34);
        }
    }
    throw new Error('Could not extract Ed25519 seed from PKCS#8 key.');
}

/**
 * Expand a partial manifest to the field set ManifestModel.model_dump() produces.
 * Python verify re-parses JSON into ManifestModel then hashes model_dump() (including
 * nulls). Browser signing must hash the same shape or signatures will not verify.
 */
function epiExpandManifestForSigning(manifest) {
    const src = manifest && typeof manifest === 'object' ? manifest : {};
    // Keys must match epi_core/schemas.py ManifestModel fields (except signature).
    const defaults = {
        analysis_error: null,
        analysis_status: null,
        approved_by: null,
        cli_command: null,
        container_format: null,
        corrected: null,
        created_at: null,
        env_snapshot_hash: null,
        failed: null,
        file_manifest: {},
        goal: null,
        governance: null,
        metrics: null,
        notes: null,
        passed: null,
        policy: null,
        public_key: null,
        source: null,
        spec_version: null,
        tags: null,
        total_llm_calls: null,
        total_steps: null,
        total_validators: null,
        trust: null,
        viewer_version: null,
        workflow_id: null,
    };
    const out = { ...defaults };
    for (const key of Object.keys(src)) {
        if (key === 'signature') continue;
        out[key] = src[key];
    }
    if (!out.file_manifest || typeof out.file_manifest !== 'object') {
        out.file_manifest = {};
    }
    // workflow_id must be canonical UUID string (Python UUID -> str())
    if (out.workflow_id != null) {
        out.workflow_id = String(out.workflow_id);
    }
    // created_at must match serialize.normalize (strip us, Z suffix)
    if (typeof out.created_at === 'string') {
        out.created_at = epiNormalizeDatetimeForCanonical(out.created_at);
    }
    return out;
}

/**
 * Sign a manifest dict the same way as epi_core/trust.py sign_manifest:
 * public_key set first, hash exclude signature, Ed25519 over SHA-256 digest,
 * signature = "ed25519:{sha256(pub_hex)[:16]}:{sig_hex}".
 */
async function epiSignManifest(manifest, seedBytes) {
    if (!globalThis.noble || !noble.signAsync) {
        throw new Error('Ed25519 signing is not available in this viewer build.');
    }
    const signed = epiExpandManifestForSigning(manifest);

    const publicKeyBytes = await noble.getPublicKeyAsync(seedBytes);
    const publicKeyHex = noble.etc.bytesToHex(publicKeyBytes);
    signed.public_key = publicKeyHex;

    // Hash the expanded shape (with nulls), excluding signature — matches get_canonical_hash.
    const jsonString = epiCanonicalJson(signed);
    const msgBytes = new TextEncoder().encode(jsonString);
    const hashArray = await epiSha256Bytes(msgBytes);
    const signatureBytes = await noble.signAsync(hashArray, seedBytes);
    const signatureHex = noble.etc.bytesToHex(signatureBytes);

    const keyNameSource = new TextEncoder().encode(publicKeyHex);
    const keyNameHash = await epiSha256Bytes(keyNameSource);
    const derivedKeyName = noble.etc.bytesToHex(keyNameHash).slice(0, 16);

    signed.signature = `ed25519:${derivedKeyName}:${signatureHex}`;
    return signed;
}

// ==========================================
// EPI Review v1.1 — artifact binding + review sign
// (matches epi_core/review.py; additive Model A)
// ==========================================

const EPI_REVIEW_VERSION = '1.1.0';
const EPI_LEGACY_REVIEW_VERSION = '1.0.0';
const EPI_REVIEW_BINDING_VERSION = '1.0.0';
const EPI_REVIEW_INDEX_VERSION = '1.0.0';

function epiAssertCanonicalReviewValue(value, path) {
    path = path || '$';
    if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
    if (typeof value === 'number') {
        if (!Number.isFinite(value) || !Number.isInteger(value)) {
            throw new Error('Floats are not allowed in signed review payloads: ' + path);
        }
        return;
    }
    if (Array.isArray(value)) {
        value.forEach((item, i) => epiAssertCanonicalReviewValue(item, path + '[' + i + ']'));
        return;
    }
    if (typeof value === 'object') {
        Object.keys(value).forEach((key) => {
            if (typeof key !== 'string') throw new Error('Review JSON object keys must be strings: ' + path);
            epiAssertCanonicalReviewValue(value[key], path + '.' + key);
        });
        return;
    }
    throw new Error('Unsupported review JSON value at ' + path + ': ' + typeof value);
}

/** Canonical JSON for review hashing — same rules as epi_core/review.py canonical_review_json. */
function epiCanonicalReviewJson(value) {
    epiAssertCanonicalReviewValue(value);
    // Prefer strict integer-safe stringify with sorted keys (no float coercion).
    const walk = (v) => {
        if (v === null) return 'null';
        if (typeof v === 'boolean') return v ? 'true' : 'false';
        if (typeof v === 'number') return JSON.stringify(v);
        if (typeof v === 'string') return JSON.stringify(v);
        if (Array.isArray(v)) return '[' + v.map(walk).join(',') + ']';
        const keys = Object.keys(v).sort();
        let out = '{';
        for (let i = 0; i < keys.length; i++) {
            if (i > 0) out += ',';
            out += JSON.stringify(keys[i]) + ':' + walk(v[keys[i]]);
        }
        return out + '}';
    };
    return walk(value);
}

async function epiComputeReviewHash(reviewPayload) {
    const payload = JSON.parse(JSON.stringify(reviewPayload || {}));
    delete payload.review_hash;
    delete payload.review_signature;
    const json = epiCanonicalReviewJson(payload);
    return epiSha256Hex(new TextEncoder().encode(json));
}

function epiSafeToken(value) {
    const token = String(value || '').trim().replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '');
    return token || 'review';
}

function epiRandomHex(nBytes) {
    const bytes = noble.etc.randomBytes(nBytes);
    return noble.etc.bytesToHex(bytes);
}

function epiMakeReviewId(reviewedAt, reviewer) {
    const timestamp = epiSafeToken(String(reviewedAt || '').replace(/:/g, '').replace(/\+/g, 'Z'));
    const reviewerToken = epiSafeToken(String(reviewer || '').toLowerCase()).slice(0, 48);
    return 'review-' + timestamp + '-' + reviewerToken + '-' + epiRandomHex(6);
}

function epiIdentityFor(reviewer) {
    const value = String(reviewer || 'reviewer');
    return {
        type: value.includes('@') ? 'email' : 'name',
        value: value,
        role: 'Reviewer',
        org: 'Unknown',
        verified: false,
    };
}

/**
 * Extract inner ZIP payload from a full .epi (envelope-v2 or legacy-zip).
 * Matches epi_core/container.py extract_inner_payload / detect logic.
 */
function epiExtractInnerZipFromEpi(epiBytes) {
    const u8 = epiBytes instanceof Uint8Array ? epiBytes : new Uint8Array(epiBytes);
    if (u8.length < 4) throw new Error('EPI file too small');
    // envelope magic "<!--"
    if (u8[0] === 0x3c && u8[1] === 0x21 && u8[2] === 0x2d && u8[3] === 0x2d) {
        if (u8.length < EPI_ENVELOPE_HEADER_SIZE) throw new Error('EPI envelope too small');
        const view = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
        // payload_length at offset 8, little-endian u64 (use low 32 bits; EPI zips fit)
        const payloadLength = view.getUint32(8, true) + view.getUint32(12, true) * 0x100000000;
        const marker = new TextEncoder().encode(EPI_ZIP_MARKER_STR);
        const scanEnd = Math.min(u8.length, EPI_ENVELOPE_HEADER_SIZE + 4 * 1024 * 1024);
        let zipStart = EPI_ENVELOPE_HEADER_SIZE;
        // Find marker after header
        outer: for (let i = EPI_ENVELOPE_HEADER_SIZE; i + marker.length <= scanEnd; i++) {
            let ok = true;
            for (let j = 0; j < marker.length; j++) {
                if (u8[i + j] !== marker[j]) { ok = false; break; }
            }
            if (ok) {
                zipStart = i + marker.length;
                break outer;
            }
        }
        // If no marker, zip starts at 128
        if (zipStart === EPI_ENVELOPE_HEADER_SIZE) {
            // confirm PK
            if (!(u8[zipStart] === 0x50 && u8[zipStart + 1] === 0x4b)) {
                // maybe polyglot without match in scan — still use header offset
            }
        }
        const zip = u8.slice(zipStart, zipStart + payloadLength);
        if (zip.length !== payloadLength) {
            throw new Error('EPI envelope payload truncated');
        }
        return { zipBytes: zip, containerFormat: 'envelope-v2' };
    }
    // legacy-zip: whole file is ZIP
    if (u8[0] === 0x50 && u8[1] === 0x4b) {
        return { zipBytes: u8.slice(), containerFormat: 'legacy-zip' };
    }
    throw new Error('Not a valid .epi file (expected envelope-v2 or ZIP)');
}

/**
 * Build artifact_binding matching epi_core/review.py build_artifact_binding.
 * memberBytesByPath: map path -> Uint8Array of uncompressed member content.
 * manifestBytes: raw bytes of manifest.json member.
 */
async function epiBuildArtifactBinding({
    workflowId,
    manifestBytes,
    manifestSignature,
    manifestPublicKey,
    fileManifestPaths,
    memberBytesByPath,
    containerFormat,
}) {
    const manifestSha = await epiSha256Hex(
        manifestBytes instanceof Uint8Array ? manifestBytes : new Uint8Array(manifestBytes)
    );
    const paths = (fileManifestPaths || []).slice().sort();
    const entries = [];
    for (const path of paths) {
        const data = memberBytesByPath && memberBytesByPath[path];
        let sha;
        if (!data) {
            sha = '__missing__';
        } else {
            sha = await epiSha256Hex(data instanceof Uint8Array ? data : new Uint8Array(data));
        }
        entries.push({ path: path, sha256: sha });
    }
    const sealedPayload = { files: entries };
    const sealedSha = await epiSha256Hex(new TextEncoder().encode(epiCanonicalReviewJson(sealedPayload)));
    return {
        binding_version: EPI_REVIEW_BINDING_VERSION,
        binding_type: 'epi_artifact',
        workflow_id: String(workflowId || ''),
        manifest_sha256: manifestSha,
        manifest_signature: manifestSignature || null,
        manifest_public_key: manifestPublicKey || null,
        sealed_evidence_sha256: sealedSha,
        container_format: containerFormat || null,
    };
}

/**
 * Sign review_hash (hex) with Ed25519 seed.
 * Wire format: ed25519:{pub_hex}:{sig_hex} over raw hash bytes (not re-hashed).
 */
async function epiSignReviewHash(reviewHashHex, seedBytes) {
    if (!globalThis.noble || !noble.signAsync) {
        throw new Error('Ed25519 signing is not available in this viewer build.');
    }
    const hashBytes = noble.etc.hexToBytes(reviewHashHex);
    const sigBytes = await noble.signAsync(hashBytes, seedBytes);
    const pub = await noble.getPublicKeyAsync(seedBytes);
    const pubHex = noble.etc.bytesToHex(pub);
    return {
        review_signature: 'ed25519:' + pubHex + ':' + noble.etc.bytesToHex(sigBytes),
        publicKeyHex: pubHex,
        fingerprint: pubHex.slice(0, 16),
    };
}

/**
 * Build a complete signed v1.1 ReviewRecord dict (Model A).
 * humanStatus: approved|rejected|escalated → ledger outcome mapping.
 */
async function epiBuildSignedReviewRecord({
    reviewedBy,
    reviewedAt,
    humanStatus,
    notes,
    artifactBinding,
    previousReviewHash,
    seedBytes,
}) {
    const outcomeMap = {
        approved: 'dismissed',
        rejected: 'confirmed_fault',
        escalated: 'skipped',
    };
    const status = String(humanStatus || 'escalated').toLowerCase();
    const reviewed_at = reviewedAt || new Date().toISOString();
    const reviewed_by = String(reviewedBy || 'reviewer');
    const review_id = epiMakeReviewId(reviewed_at, reviewed_by);

    const record = {
        review_id: review_id,
        review_version: EPI_REVIEW_VERSION,
        reviewer_identity: epiIdentityFor(reviewed_by),
        reviewed_by: reviewed_by,
        reviewed_at: reviewed_at,
        reviews: [{
            fault_step: null,
            rule_id: null,
            fault_type: null,
            outcome: outcomeMap[status] || 'skipped',
            notes: notes || '',
            reviewer: reviewed_by,
            timestamp: reviewed_at,
        }],
        artifact_binding: artifactBinding,
        previous_review_hash: previousReviewHash || null,
        review_hash: null,
        review_signature: null,
        case_level_review: true,
        certification_level: 'audit',
    };

    const review_hash = await epiComputeReviewHash(record);
    record.review_hash = review_hash;
    const signed = await epiSignReviewHash(review_hash, seedBytes);
    record.review_signature = signed.review_signature;

    return {
        record: record,
        review_id: review_id,
        keyInfo: {
            source: 'review',
            fingerprint: signed.fingerprint,
            publicKeyHex: signed.publicKeyHex,
        },
    };
}

function epiBuildReviewIndex(records, latestReviewId) {
    return {
        review_index_version: EPI_REVIEW_INDEX_VERSION,
        latest_review_id: latestReviewId || null,
        reviews: (records || [])
            .filter((r) => r && r.review_id)
            .map((r) => ({
                review_id: r.review_id,
                path: 'reviews/' + r.review_id + '.json',
                reviewed_by: r.reviewed_by,
                reviewed_at: r.reviewed_at,
                review_hash: r.review_hash,
                previous_review_hash: r.previous_review_hash || null,
                review_version: r.review_version,
                case_level_review: Boolean(r.case_level_review),
            })),
    };
}

// Expose for Node regression tests and both viewer apps
globalThis.epiWrapEnvelopeV2 = epiWrapEnvelopeV2;
globalThis.epiSignManifest = epiSignManifest;
globalThis.epiResolveSigningSeed = epiResolveSigningSeed;
globalThis.epiPackEnvelopeHeader = epiPackEnvelopeHeader;
globalThis.epiSha256Hex = epiSha256Hex;
globalThis.epiSha256Bytes = epiSha256Bytes;
globalThis.EPI_LEGACY_MIMETYPE = EPI_LEGACY_MIMETYPE;
globalThis.EPI_ENVELOPE_HEADER_SIZE = EPI_ENVELOPE_HEADER_SIZE;
globalThis.EPI_ENVELOPE_MAGIC = EPI_ENVELOPE_MAGIC;
globalThis.EPI_ZIP_MARKER_STR = EPI_ZIP_MARKER_STR;
globalThis.epiCanonicalReviewJson = epiCanonicalReviewJson;
globalThis.epiComputeReviewHash = epiComputeReviewHash;
globalThis.epiBuildArtifactBinding = epiBuildArtifactBinding;
globalThis.epiExtractInnerZipFromEpi = epiExtractInnerZipFromEpi;
globalThis.epiSignReviewHash = epiSignReviewHash;
globalThis.epiBuildSignedReviewRecord = epiBuildSignedReviewRecord;
globalThis.epiBuildReviewIndex = epiBuildReviewIndex;
globalThis.epiMakeReviewId = epiMakeReviewId;
globalThis.epiIdentityFor = epiIdentityFor;
globalThis.EPI_REVIEW_VERSION = EPI_REVIEW_VERSION;


