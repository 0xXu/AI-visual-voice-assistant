import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const originalMediaDevicesDescriptor = Object.getOwnPropertyDescriptor(
  navigator,
  "mediaDevices",
);

function createMediaFixture() {
  const stream = {
    getTracks: () => [],
    getAudioTracks: () => [{ enabled: true }],
    getVideoTracks: () => [{ enabled: true }],
  } as unknown as MediaStream;
  const getUserMedia = vi.fn().mockResolvedValue(stream);
  const enumerateDevices = vi.fn().mockResolvedValue([
    { deviceId: "cam-1", kind: "videoinput", label: "前置摄像头" },
    { deviceId: "mic-1", kind: "audioinput", label: "内置麦克风" },
  ]);

  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia, enumerateDevices },
  });

  return { getUserMedia };
}

afterEach(() => {
  cleanup();

  if (originalMediaDevicesDescriptor) {
    Object.defineProperty(
      navigator,
      "mediaDevices",
      originalMediaDevicesDescriptor,
    );
  } else {
    Reflect.deleteProperty(navigator, "mediaDevices");
  }
});

describe("App", () => {
  it("首次加载只显示入口且不请求媒体权限", () => {
    const getUserMedia = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });

    render(<App />);

    expect(screen.getByText("EchoSight")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "开始视觉对话" }),
    ).toBeInTheDocument();
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it("点击开始后请求设备并显示检测页面", async () => {
    const { getUserMedia } = createMediaFixture();

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "开始视觉对话" }));

    expect(await screen.findByText("检查摄像头与麦克风")).toBeInTheDocument();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  it("确认设备后启动会话并在 connected 前不发送媒体", async () => {
    createMediaFixture();
    const start = vi.fn();
    const createOrchestrator = vi.fn(() => ({
      start,
      sendText: vi.fn(),
      setMuted: vi.fn(),
      setVideoPaused: vi.fn(),
      stop: vi.fn(),
      destroy: vi.fn(),
    }));

    render(<App createOrchestrator={createOrchestrator} />);

    fireEvent.click(screen.getByRole("button", { name: "开始视觉对话" }));
    fireEvent.click(await screen.findByRole("button", { name: "开始会话" }));

    expect(start).toHaveBeenCalledTimes(1);
    expect(screen.getByText("正在连接")).toBeInTheDocument();
  });

  it("实时会话中可以打开记录抽屉并发送文字提问", async () => {
    createMediaFixture();
    const sendText = vi.fn();
    const createOrchestrator = vi.fn(() => ({
      start: vi.fn(),
      sendText,
      setMuted: vi.fn(),
      setVideoPaused: vi.fn(),
      stop: vi.fn(),
      destroy: vi.fn(),
    }));

    render(<App createOrchestrator={createOrchestrator} />);

    fireEvent.click(screen.getByRole("button", { name: "开始视觉对话" }));
    fireEvent.click(await screen.findByRole("button", { name: "开始会话" }));
    fireEvent.click(screen.getByRole("button", { name: "查看对话记录" }));
    fireEvent.change(screen.getByLabelText("文字提问"), {
      target: { value: "帮我看看桌面" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(sendText).toHaveBeenCalledWith("帮我看看桌面");
    expect(screen.getByLabelText("文字提问")).toHaveValue("");
  });
});
