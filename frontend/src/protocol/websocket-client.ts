import {
  type ClientMessage,
  parseServerMessage,
  type ServerMessage,
} from "./messages";

export type WebSocketState = "connecting" | "open" | "closed" | "error";

export interface WebSocketClientOptions {
  url: string;
  onMessage: (message: ServerMessage) => void;
  onStateChange: (state: WebSocketState) => void;
}

export class WebSocketClient {
  private socket: WebSocket | null = null;

  constructor(private readonly options: WebSocketClientOptions) {}

  connect(): void {
    if (
      this.socket?.readyState === WebSocket.OPEN ||
      this.socket?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    this.options.onStateChange("connecting");
    const socket = new WebSocket(this.options.url);
    this.socket = socket;

    socket.addEventListener("open", () => {
      this.options.onStateChange("open");
    });

    socket.addEventListener("message", (event) => {
      try {
        const message = parseServerMessage(String(event.data));
        if (message.type === "ping") {
          this.send({ type: "pong", data: "" });
        }
        this.options.onMessage(message);
      } catch {
        this.options.onStateChange("error");
      }
    });

    socket.addEventListener("error", () => {
      this.options.onStateChange("error");
    });

    socket.addEventListener("close", () => {
      if (this.socket === socket) {
        this.socket = null;
      }
      this.options.onStateChange("closed");
    });
  }

  send(message: ClientMessage): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) {
      return false;
    }
    this.socket.send(JSON.stringify(message));
    return true;
  }

  get bufferedAmount(): number {
    return this.socket?.bufferedAmount ?? 0;
  }

  close(): void {
    const socket = this.socket;
    this.socket = null;
    if (
      socket?.readyState === WebSocket.OPEN ||
      socket?.readyState === WebSocket.CONNECTING
    ) {
      socket.close(1000, "客户端结束连接");
    }
  }
}
