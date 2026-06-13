import { afterEach, describe, expect, it, vi } from "vitest";
import { WebSocketClient } from "./websocket-client";

class FakeWebSocket extends EventTarget {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readonly sent: string[] = [];
  readyState = FakeWebSocket.CONNECTING;
  bufferedAmount = 0;

  constructor(readonly url: string) {
    super();
    FakeWebSocket.instances.push(this);
  }

  static instances: FakeWebSocket[] = [];

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.dispatchEvent(new Event("open"));
  }

  receive(data: string) {
    this.dispatchEvent(new MessageEvent("message", { data }));
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.dispatchEvent(new CloseEvent("close", { code: 1000, wasClean: true }));
  }

  abnormalClose() {
    this.readyState = FakeWebSocket.CLOSED;
    this.dispatchEvent(new CloseEvent("close", { code: 1006, wasClean: false }));
  }
}

const originalWebSocket = globalThis.WebSocket;

afterEach(() => {
  vi.useRealTimers();
  FakeWebSocket.instances = [];
  globalThis.WebSocket = originalWebSocket;
});

describe("WebSocketClient", () => {
  it("收到服务端 ping 时回复 pong 并继续分发消息", () => {
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    const onMessage = vi.fn();
    const client = new WebSocketClient({
      url: "ws://localhost:8000/ws",
      onMessage,
      onStateChange: vi.fn(),
    });

    client.connect();
    const socket = FakeWebSocket.instances[0];
    socket.open();
    socket.receive('{"type":"ping","data":""}');

    expect(socket.sent).toEqual(['{"type":"pong","data":""}']);
    expect(onMessage).toHaveBeenCalledWith({ type: "ping", data: "" });
  });

  it("未连接时不发送客户端消息", () => {
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    const client = new WebSocketClient({
      url: "ws://localhost:8000/ws",
      onMessage: vi.fn(),
      onStateChange: vi.fn(),
    });

    expect(client.send({ type: "start_session", data: "" })).toBe(false);
  });

  it("异常关闭时最多按退避重连三次", () => {
    vi.useFakeTimers();
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    const onStateChange = vi.fn();
    const client = new WebSocketClient({
      url: "ws://localhost:8000/ws",
      onMessage: vi.fn(),
      onStateChange,
    });

    client.connect();
    FakeWebSocket.instances[0].open();
    FakeWebSocket.instances[0].abnormalClose();
    expect(onStateChange).toHaveBeenCalledWith("recovering");

    vi.advanceTimersByTime(500);
    expect(FakeWebSocket.instances).toHaveLength(2);

    FakeWebSocket.instances[1].abnormalClose();
    vi.advanceTimersByTime(1000);
    expect(FakeWebSocket.instances).toHaveLength(3);

    FakeWebSocket.instances[2].abnormalClose();
    vi.advanceTimersByTime(2000);
    expect(FakeWebSocket.instances).toHaveLength(4);

    FakeWebSocket.instances[3].abnormalClose();
    vi.advanceTimersByTime(2000);
    expect(FakeWebSocket.instances).toHaveLength(4);
    expect(onStateChange).toHaveBeenLastCalledWith("closed");
  });
});
