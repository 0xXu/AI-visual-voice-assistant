import {
  type ClientMessage,
  parseServerMessage,
  type ServerMessage,
} from "./messages";

export type WebSocketState =
  | "connecting"
  | "open"
  | "closed"
  | "error"
  | "failed"
  | "recovering";

export interface WebSocketClientOptions {
  url: string;
  onMessage: (message: ServerMessage) => void;
  onStateChange: (state: WebSocketState) => void;
}

export class WebSocketClient {
  private socket: WebSocket | null = null;
  private reconnectAttempts = 0;
  private readonly reconnectDelays = [500, 1000, 2000];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private manuallyClosed = false;

  constructor(private readonly options: WebSocketClientOptions) {}

  connect(): void {
    if (
      this.socket?.readyState === WebSocket.OPEN ||
      this.socket?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    this.manuallyClosed = false;
    this.openSocket();
  }

  private openSocket(): void {
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
        if (message.type === "status" && message.data === "connected") {
          this.reconnectAttempts = 0;
        }
        this.options.onMessage(message);
      } catch {
        this.options.onStateChange("error");
      }
    });

    socket.addEventListener("error", () => {
      this.options.onStateChange("error");
    });

    socket.addEventListener("close", (event) => {
      if (this.socket === socket) {
        this.socket = null;
      }
      if (this.shouldReconnect(event)) {
        this.scheduleReconnect();
      } else if (
        !this.manuallyClosed &&
        (!event.wasClean || event.code !== 1000)
      ) {
        this.options.onStateChange("failed");
      } else {
        this.options.onStateChange("closed");
      }
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
    this.manuallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const socket = this.socket;
    this.socket = null;
    if (
      socket?.readyState === WebSocket.OPEN ||
      socket?.readyState === WebSocket.CONNECTING
    ) {
      socket.close(1000, "客户端结束连接");
    }
  }

  private shouldReconnect(event: CloseEvent): boolean {
    return (
      !this.manuallyClosed &&
      (!event.wasClean || event.code !== 1000) &&
      this.reconnectAttempts < this.reconnectDelays.length
    );
  }

  private scheduleReconnect(): void {
    const delay = this.reconnectDelays[this.reconnectAttempts];
    this.reconnectAttempts += 1;
    this.options.onStateChange("recovering");
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, delay);
  }
}
