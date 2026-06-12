import { describe, expect, it, vi } from "vitest";
import { VideoFrameSampler } from "./video-frame-sampler";

describe("VideoFrameSampler", () => {
  it("为每帧生成递增序列和当前时间戳", () => {
    const sampler = new VideoFrameSampler({
      video: document.createElement("video"),
      onFrame: vi.fn(),
      getBufferedAmount: () => 0,
      now: () => 1781234567890,
    });

    expect(sampler.nextMetadata()).toEqual({
      sequence: 1,
      timestamp: 1781234567890,
    });
    expect(sampler.nextMetadata().sequence).toBe(2);
  });

  it("网络缓冲过高或页面不可见时跳过帧", () => {
    const sampler = new VideoFrameSampler({
      video: document.createElement("video"),
      onFrame: vi.fn(),
      getBufferedAmount: () => 0,
    });

    expect(sampler.shouldSkipFrame(300_000, true)).toBe(true);
    expect(sampler.shouldSkipFrame(0, false)).toBe(true);
    expect(sampler.shouldSkipFrame(0, true)).toBe(false);
  });
});
