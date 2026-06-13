import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionSummary } from "./SessionSummary";

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

afterEach(() => {
  cleanup();
});

describe("SessionSummary", () => {
  it("终止状态收到 usage 后展示结果", () => {
    const { rerender } = render(
      <SessionSummary
        terminalStatus="budget_exceeded"
        usage={null}
        messages={[]}
        onRestart={vi.fn()}
        onOpenTranscript={vi.fn()}
      />,
    );

    expect(screen.getByText("正在整理本次会话")).toBeInTheDocument();

    rerender(
      <SessionSummary
        terminalStatus="budget_exceeded"
        usage={usage}
        messages={[]}
        onRestart={vi.fn()}
        onOpenTranscript={vi.fn()}
      />,
    );

    expect(screen.getByText("已达到本次会话额度")).toBeInTheDocument();
    expect(screen.getByText("1,540")).toBeInTheDocument();
    expect(screen.getByText("00:25")).toBeInTheDocument();
    expect(screen.getByText("480 ms")).toBeInTheDocument();
  });

  it("可以重新开始或打开记录", () => {
    const onRestart = vi.fn();
    const onOpenTranscript = vi.fn();

    render(
      <SessionSummary
        terminalStatus="stopped"
        usage={usage}
        messages={[]}
        onRestart={onRestart}
        onOpenTranscript={onOpenTranscript}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "再次开始" }));
    fireEvent.click(screen.getByRole("button", { name: "查看对话记录" }));

    expect(onRestart).toHaveBeenCalledTimes(1);
    expect(onOpenTranscript).toHaveBeenCalledTimes(1);
  });
});
