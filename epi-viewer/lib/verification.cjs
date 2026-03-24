const crypto = require('crypto');

const ED25519_SPKI_PREFIX = Buffer.from('302a300506032b6570032100', 'hex');
const ISO_UTC_DATETIME_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;

function normalizeScalar(value) {
    if (typeof value === 'string' && ISO_UTC_DATETIME_RE.test(value)) {
        const noFraction = value.replace(/\.\d+Z$/, 'Z');
        return noFraction.replace(/Z$/, '+00:00Z');
    }

    return value;
}

function canonicalJSONStringify(value) {
    if (value === null || typeof value !== 'object') {
        return JSON.stringify(normalizeScalar(value));
    }

    if (Array.isArray(value)) {
        return `[${value.map((item) => canonicalJSONStringify(item)).join(',')}]`;
    }

    const keys = Object.keys(value).sort();
    const body = keys
        .map((key) => `${JSON.stringify(key)}:${canonicalJSONStringify(value[key])}`)
        .join(',');
    return `{${body}}`;
}

function getSpecMajorVersion(specVersion) {
    const match = String(specVersion || '').match(/^(\d+)/);
    return match ? Number.parseInt(match[1], 10) : 1;
}

function getManifestHashBytes(manifest) {
    const majorVersion = getSpecMajorVersion(manifest.spec_version);
    if (majorVersion < 2) {
        throw new Error(
            `Unsupported legacy spec_version "${manifest.spec_version || 'unknown'}" for desktop verification`
        );
    }

    const manifestWithoutSignature = { ...manifest };
    delete manifestWithoutSignature.signature;

    const canonicalJson = canonicalJSONStringify(manifestWithoutSignature);
    return crypto.createHash('sha256').update(Buffer.from(canonicalJson, 'utf8')).digest();
}

function decodeHexOrBase64(value, label) {
    const normalized = String(value || '').trim();
    if (!normalized) {
        throw new Error(`Missing ${label}`);
    }

    if (/^[0-9a-fA-F]+$/.test(normalized) && normalized.length % 2 === 0) {
        return Buffer.from(normalized, 'hex');
    }

    const base64Bytes = Buffer.from(normalized, 'base64');
    if (base64Bytes.length === 0) {
        throw new Error(`Invalid ${label} encoding`);
    }

    return base64Bytes;
}

function createEd25519PublicKey(publicKeyBytes) {
    if (publicKeyBytes.length !== 32) {
        throw new Error(`Embedded public key must be 32 bytes, got ${publicKeyBytes.length}`);
    }

    return crypto.createPublicKey({
        key: Buffer.concat([ED25519_SPKI_PREFIX, Buffer.from(publicKeyBytes)]),
        format: 'der',
        type: 'spki'
    });
}

async function verifyManifestSignature(manifest) {
    try {
        if (!manifest.signature) {
            return {
                valid: false,
                error: 'No signature present',
                level: 'UNSIGNED'
            };
        }

        if (!manifest.public_key) {
            return {
                valid: false,
                error: 'No public key embedded in manifest'
            };
        }

        const parts = manifest.signature.split(':', 3);
        if (parts.length !== 3) {
            return {
                valid: false,
                error: 'Invalid signature format'
            };
        }

        const [algorithm, keyName, encodedSignature] = parts;
        if (algorithm !== 'ed25519') {
            return {
                valid: false,
                error: `Unsupported algorithm: ${algorithm}`
            };
        }

        const signatureBytes = decodeHexOrBase64(encodedSignature, 'signature');
        if (signatureBytes.length !== 64) {
            return {
                valid: false,
                error: `Invalid signature length: expected 64 bytes, got ${signatureBytes.length}`
            };
        }

        const publicKeyBytes = decodeHexOrBase64(manifest.public_key, 'embedded public key');
        const publicKey = createEd25519PublicKey(publicKeyBytes);
        const manifestHashBytes = getManifestHashBytes(manifest);

        const isValid = crypto.verify(null, manifestHashBytes, publicKey, signatureBytes);
        if (!isValid) {
            return {
                valid: false,
                error: 'Invalid signature - data may have been tampered',
                algorithm,
                keyName,
                level: 'INVALID'
            };
        }

        return {
            valid: true,
            algorithm,
            keyName,
            level: 'SIGNED'
        };
    } catch (error) {
        return {
            valid: false,
            error: error.message
        };
    }
}

module.exports = {
    canonicalJSONStringify,
    decodeHexOrBase64,
    getManifestHashBytes,
    verifyManifestSignature
};
