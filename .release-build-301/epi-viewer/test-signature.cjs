const crypto = require('crypto');
const assert = require('assert');
const { getManifestHashBytes, verifyManifestSignature } = require('./lib/verification.cjs');

const SPKI_PREFIX_HEX = '302a300506032b6570032100';

const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
const publicKeyDer = publicKey.export({ format: 'der', type: 'spki' });
const prefixLength = Buffer.from(SPKI_PREFIX_HEX, 'hex').length;
const publicKeyHex = publicKeyDer.subarray(prefixLength).toString('hex');

const unsignedManifest = {
    spec_version: '2.8.8',
    workflow_id: '5034ae3b-f9ac-48d8-89c8-3906fd7570cb',
    created_at: '2026-03-23T14:40:11.823075Z',
    cli_command: 'epi test',
    env_snapshot_hash: null,
    file_manifest: {
        'steps.jsonl': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    },
    public_key: publicKeyHex,
    goal: 'verify viewer signature test',
    notes: null,
    metrics: null,
    approved_by: null,
    tags: null
};

const manifestHash = getManifestHashBytes(unsignedManifest);
const signatureHex = crypto.sign(null, manifestHash, privateKey).toString('hex');
const signedManifest = {
    ...unsignedManifest,
    signature: `ed25519:desktop-test:${signatureHex}`
};

(async () => {
    const valid = await verifyManifestSignature(signedManifest);
    assert.equal(valid.valid, true, `Expected valid signature, got: ${JSON.stringify(valid)}`);

    const tamperedManifest = {
        ...signedManifest,
        file_manifest: {
            ...signedManifest.file_manifest,
            'steps.jsonl': 'b'.repeat(64)
        }
    };
    const tampered = await verifyManifestSignature(tamperedManifest);
    assert.equal(tampered.valid, false, 'Tampered manifest should fail verification');

    const malformed = await verifyManifestSignature({
        ...signedManifest,
        signature: 'ed25519:test:not-hex-or-base64!!!'
    });
    assert.equal(malformed.valid, false, 'Malformed signature should fail verification');

    console.log('EPI Viewer signature verification tests passed');
})().catch((error) => {
    console.error(error);
    process.exit(1);
});
