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

    return { verifyAsync, etc };
})();

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

    // Recursive canonical JSON stringify
    const canonicalJson = (obj) => {
        if (Array.isArray(obj)) {
            return '[' + obj.map(canonicalJson).join(',') + ']';
        } else if (typeof obj === 'object' && obj !== null) {
            const keys = Object.keys(obj).sort();
            let result = '{';
            for (let i = 0; i < keys.length; i++) {
                const key = keys[i];
                if (i > 0) result += ',';
                result += JSON.stringify(key) + ':' + canonicalJson(obj[key]);
            }
            result += '}';
            return result;
        } else {
            return JSON.stringify(obj);
        }
    };

    const jsonString = canonicalJson(manifestCopy);
    const msgBytes = new TextEncoder().encode(jsonString);

    try {
        // 5. Verify Hash
        // The backend signs the SHA-256 hash of the content.
        // So we must convert content -> SHA-256 hash -> verify against signature
        const hashBuffer = await crypto.subtle.digest('SHA-256', msgBytes);
        const hashArray = new Uint8Array(hashBuffer);

        const sigBytes = noble.etc.hexToBytes(sigHex);

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

