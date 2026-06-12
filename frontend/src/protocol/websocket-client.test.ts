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
    this.dispatchEvent(new CloseEvent("close"));
  }
}

const originalWebSocket = globalThis.WebSocket;

afterEach(() => {
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
});
