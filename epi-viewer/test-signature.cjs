const assert = require('assert');
const { verifyManifestSignature } = require('./lib/verification.cjs');

const signedManifest = {
    spec_version: '2.8.7',
    workflow_id: '5034ae3b-f9ac-48d8-89c8-3906fd7570cb',
    created_at: '2026-03-23T14:40:11.823075Z',
    cli_command: 'epi test',
    env_snapshot_hash: null,
    file_manifest: {
        'steps.jsonl': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    },
    public_key: '9bbb58dbda29c5f71a6e1312e7a1f1d74c5c63269b25e2aa08a92995f98bdf30',
    signature: 'ed25519:desktop-test:23902b4813d8d11f495b0794c02bb148f383b3eddb13c1b50adf2e02f52e3a912ea15f02f14cc17c37b6f33a493709e879360381db51ca2695fda9ac2222bb00',
    goal: 'verify viewer signature test',
    notes: null,
    metrics: null,
    approved_by: null,
    tags: null
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
