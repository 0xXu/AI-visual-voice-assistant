import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const originalMediaDevicesDescriptor = Object.getOwnPropertyDescriptor(
  navigator,
  "mediaDevices",
);

afterEach(() => {
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
});
