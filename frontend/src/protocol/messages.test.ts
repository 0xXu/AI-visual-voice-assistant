import { describe, expect, it } from "vitest";
import { parseServerMessage } from "./messages";

describe("parseServerMessage", () => {
  it("解析已发布的连接状态事件", () => {
    expect(parseServerMessage('{"type":"status","data":"connected"}')).toEqual(
      {
        type: "status",
        data: "connected",
      },
    );
  });

  it("把未来未知事件转换为 unknown", () => {
    expect(parseServerMessage('{"type":"future","data":1}')).toEqual({
      type: "unknown",
      originalType: "future",
      data: 1,
    });
  });

  it("拒绝非对象消息", () => {
    expect(() => parseServerMessage("[]")).toThrow("服务端消息格式无效");
  });

  it("解析 usage 事件", () => {
    expect(
      parseServerMessage(
        '{"type":"usage","data":{"audio_bytes":32000,"text_chars":20,"video_frames":8,"video_replaced_frames":2,"video_bytes":180000,"input_tokens":1200,"output_tokens":340,"total_tokens":1540,"duration_ms":25000,"first_response_latency_ms":480}}',
      ),
    ).toEqual({
      type: "usage",
      data: {
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
      },
    });
  });
});
