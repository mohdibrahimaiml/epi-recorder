import { describe, expect, it } from "vitest";
import { openSecret, sealSecret } from "../src/lib/secretbox.ts";

const BOX_KEY = "ab".repeat(32);

describe("AES-GCM inbox secret box", () => {
  it("round-trips the HMAC secret", async () => {
    const sealed = await sealSecret(BOX_KEY, "vendor-shared-secret");
    expect(sealed).not.toContain("vendor-shared-secret");
    expect(await openSecret(BOX_KEY, sealed)).toBe("vendor-shared-secret");
  });
  it("rejects the wrong key and tampered boxes", async () => {
    const sealed = await sealSecret(BOX_KEY, "s3cr3t");
    await expect(openSecret("cd".repeat(32), sealed)).rejects.toThrow();
    const raw = Buffer.from(sealed, "base64");
    raw[raw.length - 1]! ^= 0x01;
    await expect(openSecret(BOX_KEY, raw.toString("base64"))).rejects.toThrow();
  });
});
