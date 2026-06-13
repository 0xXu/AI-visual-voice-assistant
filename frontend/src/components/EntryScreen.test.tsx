import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EntryScreen } from "./EntryScreen";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EntryScreen", () => {
  it("渲染强烈舞台首屏且保留开始操作", () => {
    const onStart = vi.fn();

    const { container } = render(<EntryScreen onStart={onStart} />);

    expect(container.querySelector(".entry-stage__beam")).toBeInTheDocument();
    expect(container.querySelector(".entry-stage__grain")).toBeInTheDocument();
    expect(container.querySelector(".entry-orbit__ticks")).toBeInTheDocument();
    expect(container.querySelector(".entry-orbit__scan")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "开始视觉对话" }));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it("将视觉与语音标签挂载为可公转的双轨卫星模块", () => {
    const { container } = render(<EntryScreen onStart={vi.fn()} />);
    const carriers = container.querySelectorAll(".entry-orbit__carrier");

    expect(carriers).toHaveLength(2);
    expect(
      container.querySelector(".entry-orbit__carrier--vision .entry-orbit__satellite"),
    ).toHaveTextContent("视觉理解");
    expect(
      container.querySelector(".entry-orbit__carrier--voice .entry-orbit__satellite"),
    ).toHaveTextContent("自然语音");
    expect(container.querySelectorAll(".entry-orbit__node")).toHaveLength(2);
  });

  it("精细指针移动会更新光场位置并在离开时复位", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: query.includes("pointer: fine"),
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
    vi.stubGlobal(
      "requestAnimationFrame",
      vi.fn((callback: FrameRequestCallback) => {
        callback(0);
        return 1;
      }),
    );

    const { container } = render(<EntryScreen onStart={vi.fn()} />);
    const stage = container.querySelector<HTMLElement>(".entry-screen");
    expect(stage).not.toBeNull();

    vi.spyOn(stage!, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      width: 1000,
      height: 800,
      top: 0,
      right: 1000,
      bottom: 800,
      left: 0,
      toJSON: () => ({}),
    });

    fireEvent.pointerMove(stage!, { clientX: 750, clientY: 200 });

    expect(stage!.style.getPropertyValue("--entry-pointer-x")).toBe("75%");
    expect(stage!.style.getPropertyValue("--entry-pointer-y")).toBe("25%");

    fireEvent.pointerLeave(stage!);

    expect(stage!.style.getPropertyValue("--entry-pointer-x")).toBe("50%");
    expect(stage!.style.getPropertyValue("--entry-pointer-y")).toBe("50%");
  });
});
