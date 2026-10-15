import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { computeManifestHash, keyFingerprint, verifyManifestSignature } from "../src/lib/manifest.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const FIXTURE = join(root, "test", "fixtures", "sample-manifest.json");

// Goldens produced by the Python implementation over the same bytes:
//   ManifestModel(**manifest) -> get_canonical_hash(exclude signature)
//   key_fingerprint(public_key, grouped=False)
const PYTHON_CANONICAL = "116addb42820dfcf6fcb632973b8ef2d77c51a518cdae6b4025258888afdd244";
const PYTHON_FINGERPRINT = "7004fce0a4a92327";

describe("manifest seal verification (ported preimage)", () => {
  it("matches the Python canonical hash byte-for-byte", async () => {
    const raw = readFileSync(FIXTURE, "utf8");
    expect(await computeManifestHash(raw)).toBe(PYTHON_CANONICAL);
  });

  it("verifies the real sealed fixture as valid", async () => {
    const raw = readFileSync(FIXTURE, "utf8");
    const r = await verifyManifestSignature(raw);
    expect(r).toEqual({ status: "valid", fingerprint: PYTHON_FINGERPRINT });
  });

  it("matches the Python key fingerprint", async () => {
    const manifest = JSON.parse(readFileSync(FIXTURE, "utf8")) as { public_key: string };
    expect(await keyFingerprint(manifest.public_key)).toBe(PYTHON_FINGERPRINT);
  });

  it("rejects a tampered manifest as invalid (not unsigned)", async () => {
    const raw = readFileSync(FIXTURE, "utf8").replace("Website sample.epi", "Website sample!epi");
    const r = await verifyManifestSignature(raw);
    expect(r.status).toBe("invalid");
  });

  it("reports a missing signature as unsigned", async () => {
    const manifest = JSON.parse(readFileSync(FIXTURE, "utf8")) as Record<string, unknown>;
    delete manifest.signature;
    const r = await verifyManifestSignature(JSON.stringify(manifest));
    expect(r).toEqual({ status: "unsigned" });
  });

  it("rejects a swapped key name as invalid", async () => {
    const manifest = JSON.parse(readFileSync(FIXTURE, "utf8")) as Record<string, unknown>;
    manifest.signature = (manifest.signature as string).replace(/^ed25519:[0-9a-f]{16}:/, "ed25519:0000000000000000:");
    const r = await verifyManifestSignature(JSON.stringify(manifest));
    expect(r.status).toBe("invalid");
  });

  it("rejects non-JSON as invalid", async () => {
    expect((await verifyManifestSignature("not json")).status).toBe("invalid");
  });
});
