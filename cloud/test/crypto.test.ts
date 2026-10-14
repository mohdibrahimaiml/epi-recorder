import { describe, expect, it } from "vitest";
import { hmacHex, newApiKey, newToken, safeEqual, sha256Hex } from "../src/lib/crypto.ts";

describe("sha256Hex", () => {
  it("matches the known SHA-256 of 'abc'", async () => {
    expect(await sha256Hex("abc")).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
});

describe("safeEqual", () => {
  it("compares exactly and in fixed time shape", () => {
    expect(safeEqual("abc", "abc")).toBe(true);
    expect(safeEqual("abc", "abd")).toBe(false);
    expect(safeEqual("abc", "abcd")).toBe(false);
  });
});

describe("hmac", () => {
  it("signs and verifies; rejects wrong secret and tampered bodies", async () => {
    const body = '{"schema":"epi-witness/v1"}';
    const hex = await hmacHex("secret", body);
    const { verifyHmac } = await import("../src/lib/crypto.ts");
    expect(await verifyHmac(`sha256=${hex}`, "secret", body)).toBe(true);
    expect(await verifyHmac(`sha256=${hex}`, "wrong", body)).toBe(false);
    expect(await verifyHmac(`sha256=${hex}`, "secret", body + "x")).toBe(false);
    expect(await verifyHmac(null, "secret", body)).toBe(false);
    expect(await verifyHmac("md5=00", "secret", body)).toBe(false);
  });
});

describe("tokens", () => {
  it("issues 32-byte hex tokens and epik_ keys", () => {
    expect(newToken()).toMatch(/^[0-9a-f]{64}$/);
    const k = newApiKey();
    expect(k.raw).toMatch(/^epik_[0-9a-f]{40}$/);
    expect(k.prefix).toBe(k.raw.slice("epik_".length, "epik_".length + 8));
  });
});
