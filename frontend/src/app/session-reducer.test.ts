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

  it("把连续 AI 文本片段追加到当前消息", () => {
    const first = sessionReducer(initialSessionState, {
      type: "MODEL_TEXT",
      text: "杯子在",
    });
    const second = sessionReducer(first, {
      type: "MODEL_TEXT",
      text: "电脑右侧",
    });

    expect(second.messages.at(-1)?.text).toBe("杯子在电脑右侧");
  });

  it("turn_complete 固化当前 AI 消息", () => {
    const stateWithStreamingAssistant: SessionState = {
      ...initialSessionState,
      phase: "speaking",
      messages: [
        {
          id: "assistant-1",
          role: "assistant",
          text: "杯子在电脑右侧",
          source: "voice",
          complete: false,
        },
      ],
    };

    const next = sessionReducer(stateWithStreamingAssistant, {
      type: "TURN_COMPLETE",
    });

    expect(next.messages.at(-1)?.complete).toBe(true);
  });

  it("把用户语音转写追加到当前语音消息", () => {
    const started = sessionReducer(initialSessionState, {
      type: "VOICE_TURN_STARTED",
    });
    const first = sessionReducer(started, {
      type: "USER_TEXT",
      text: "桌上这个",
    });
    const second = sessionReducer(first, {
      type: "USER_TEXT",
      text: "是什么？",
    });

    expect(second.messages).toHaveLength(1);
    expect(second.messages.at(-1)?.text).toBe("桌上这个是什么？");
  });

  it("语音占位未完成时不会重复插入", () => {
    const first = sessionReducer(initialSessionState, {
      type: "VOICE_TURN_STARTED",
    });
    const second = sessionReducer(first, {
      type: "VOICE_TURN_STARTED",
    });

    expect(second.messages).toHaveLength(1);
    expect(second.messages.at(-1)?.text).toBe("语音提问");
  });
});
