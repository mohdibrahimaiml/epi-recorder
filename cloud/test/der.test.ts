import { describe, expect, it } from "vitest";
import { encodeTimestampReq, parseTimestampResp, parseTLV } from "../src/lib/der.ts";

const GOLDEN_REQ_HEX =
  "303c0201013031300d060960864801650304020105000420" + "aa".repeat(32) + "0204075bcd15";

describe("RFC 3161 DER", () => {
  it("encodes TimeStampReq byte-identical to asn1crypto (nonce 123456789)", () => {
    const digest = new Uint8Array(32).fill(0xaa);
    expect(Buffer.from(encodeTimestampReq(digest, 123456789)).toString("hex")).toBe(GOLDEN_REQ_HEX);
  });
  it("rejects bad inputs", () => {
    expect(() => encodeTimestampReq(new Uint8Array(31), 1)).toThrow();
    expect(() => encodeTimestampReq(new Uint8Array(32), 0)).toThrow();
  });
  it("parses a TimeStampResp status + token", () => {
    // status=granted(0), token [0] EXPLICIT holding 4 bytes.
    const resp = new Uint8Array([0x30, 0x0b, 0x30, 0x03, 0x02, 0x01, 0x00, 0xa0, 0x04, 0x04, 0x02, 0xde, 0xad]);
    const p = parseTimestampResp(resp);
    expect(p.status).toBe(0);
    expect(p.tokenRaw && Buffer.from(p.tokenRaw).toString("hex")).toBe("a0040402dead");
    // No token present.
    const bare = new Uint8Array([0x30, 0x05, 0x30, 0x03, 0x02, 0x01, 0x02]);
    const q = parseTimestampResp(bare);
    expect(q.status).toBe(2);
    expect(q.tokenRaw).toBeNull();
  });
  it("rejects truncated DER", () => {
    expect(() => parseTLV(new Uint8Array([0x30, 0x05, 0x02]))).toThrow();
    expect(() => parseTimestampResp(new Uint8Array([0x04, 0x01, 0x00]))).toThrow();
  });
});
