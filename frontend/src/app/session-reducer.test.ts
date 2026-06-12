import { describe, expect, it } from "vitest";
import {
  initialSessionState,
  sessionReducer,
  type SessionState,
} from "./session-reducer";

describe("sessionReducer", () => {
  it("连接成功后进入 listening", () => {
    expect(
      sessionReducer(initialSessionState, { type: "SESSION_CONNECTED" }).phase,
    ).toBe("listening");
  });

  it("模型被打断后回到 listening", () => {
    expect(
      sessionReducer(
        { ...initialSessionState, phase: "speaking" },
        { type: "MODEL_INTERRUPTED" },
      ).phase,
    ).toBe("listening");
  });

  it("终止状态先进入 ending 并记录原因", () => {
    const stopped = sessionReducer(initialSessionState, {
      type: "SESSION_TERMINATED",
      status: "max_duration",
    });

    expect(stopped.phase).toBe("ending");
    expect(stopped.terminalStatus).toBe("max_duration");
  });

  it("只有 ending 阶段收到 usage 后进入 ended", () => {
    const usage = {
      audio_bytes: 32000,
      text_chars: 20,
      video_frames: 8,
      video_replaced_frames: 2,
      video_bytes: 180000,
      input_tokens: 1200,
      output_tokens: 340,
      total_tokens: 1540,
      duration_ms: 25000,
      first_response_latency_ms: 480,
    };
    const ending: SessionState = {
      ...initialSessionState,
      phase: "ending",
      terminalStatus: "budget_exceeded",
    };

    expect(
      sessionReducer(initialSessionState, {
        type: "USAGE_RECEIVED",
        usage,
      }).phase,
    ).toBe("idle");
    expect(
      sessionReducer(ending, {
        type: "USAGE_RECEIVED",
        usage,
      }).phase,
    ).toBe("ended");
  });
});
