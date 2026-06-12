import { describe, expect, it } from "vitest";
import {
  base64ToBytes,
  bytesToBase64,
  floatToPcm16,
  pcm16Base64ToFloat32,
} from "./audio-codec";

describe("audio codec", () => {
  it("把浮点采样限制并转换为 PCM16", () => {
    expect(Array.from(floatToPcm16(new Float32Array([-2, -1, 0, 1, 2]))))
      .toEqual([-32768, -32768, 0, 32767, 32767]);
  });

  it("解码小端 PCM16 Base64", () => {
    expect(Array.from(pcm16Base64ToFloat32("AACA/w==")))
      .toEqual([0, -0.00390625]);
  });

  it("往返转换字节和 Base64", () => {
    expect(Array.from(base64ToBytes(bytesToBase64(new Uint8Array([1, 2, 3])))))
      .toEqual([1, 2, 3]);
  });
});
