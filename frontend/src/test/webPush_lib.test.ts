/**
 * Unit tests for frontend/src/lib/webPush.ts pure helpers.
 *
 * Hard guarantees verified here:
 *   - base64UrlToArrayBuffer returns a real ArrayBuffer (the type
 *     PushManager.subscribe({ applicationServerKey }) expects), not
 *     a Uint8Array — fixes the v3.15.16.N2b2b production tsc build
 *     failure where Uint8Array<ArrayBufferLike> was rejected as
 *     not assignable to BufferSource.
 *   - The byte content of the returned buffer matches the decoded
 *     base64url input.
 *   - Empty input is tolerated.
 *   - Padding-less and standard padded inputs both decode correctly.
 */

import { describe, expect, it } from "vitest";

import { base64UrlToArrayBuffer } from "../lib/webPush";

describe("base64UrlToArrayBuffer", () => {
  it("returns an ArrayBuffer (not a Uint8Array)", () => {
    const buf = base64UrlToArrayBuffer("BCfV1eK4");
    // ArrayBuffer is the type PushManager wants. A Uint8Array's
    // .buffer would also be an ArrayBuffer but the *return value*
    // must itself be an ArrayBuffer.
    expect(buf).toBeInstanceOf(ArrayBuffer);
    expect(buf instanceof Uint8Array).toBe(false);
  });

  it("byteLength matches the decoded base64 length", () => {
    // "Hello" in base64 is "SGVsbG8=" (5 bytes decoded).
    // base64url variant: "SGVsbG8" (no padding required for this length).
    const buf = base64UrlToArrayBuffer("SGVsbG8");
    expect(buf.byteLength).toBe(5);
  });

  it("decodes content correctly into the buffer", () => {
    const buf = base64UrlToArrayBuffer("SGVsbG8");
    const view = new Uint8Array(buf);
    // 'H' 'e' 'l' 'l' 'o'
    expect(Array.from(view)).toEqual([72, 101, 108, 108, 111]);
  });

  it("tolerates inputs that need padding restoration", () => {
    // "M" base64 is "TQ==" (1 byte). base64url: "TQ".
    const buf = base64UrlToArrayBuffer("TQ");
    expect(buf.byteLength).toBe(1);
    expect(new Uint8Array(buf)[0]).toBe(0x4d);
  });

  it("handles base64url-specific characters (- and _)", () => {
    // 0xff,0xff base64 is "//8=", base64url is "__8".
    const buf = base64UrlToArrayBuffer("__8");
    expect(buf.byteLength).toBe(2);
    expect(new Uint8Array(buf)).toEqual(new Uint8Array([0xff, 0xff]));
    // 0xfb,0xff base64 is "+/8=", base64url is "-_8".
    const buf2 = base64UrlToArrayBuffer("-_8");
    expect(new Uint8Array(buf2)).toEqual(new Uint8Array([0xfb, 0xff]));
  });

  it("empty string yields a zero-length ArrayBuffer", () => {
    const buf = base64UrlToArrayBuffer("");
    expect(buf).toBeInstanceOf(ArrayBuffer);
    expect(buf.byteLength).toBe(0);
  });
});
