export type TerminalStatus =
  | "stopped"
  | "idle_timeout"
  | "max_duration"
  | "budget_exceeded";

export interface UsageData {
  audio_bytes: number;
  text_chars: number;
  video_frames: number;
  video_replaced_frames: number;
  video_bytes: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  duration_ms: number;
  first_response_latency_ms: number | null;
}

export type ServerMessage =
  | { type: "status"; data: "connected" | TerminalStatus }
  | { type: "text"; data: string }
  | { type: "user_text"; data: string }
  | { type: "audio"; data: string }
  | { type: "turn_complete"; data: "" }
  | { type: "interrupted"; data: "" }
  | { type: "ping"; data: "" }
  | { type: "pong"; data: "" }
  | { type: "error"; data: string }
  | { type: "go_away"; data: { time_left_ms: number } }
  | { type: "session_resumption"; data: { resumable: boolean } }
  | { type: "usage"; data: UsageData }
  | { type: "unknown"; originalType: string; data: unknown };

export type ClientMessage =
  | { type: "start_session"; data: "" }
  | { type: "stop_session"; data: "" }
  | { type: "ping"; data: "" }
  | { type: "pong"; data: "" }
  | { type: "text"; data: string }
  | { type: "audio"; data: string }
  | {
      type: "video_frame";
      data: string;
      timestamp: number;
      sequence: number;
    };

type RawMessage = Record<string, unknown>;

const knownTypes = new Set([
  "status",
  "text",
  "user_text",
  "audio",
  "turn_complete",
  "interrupted",
  "ping",
  "pong",
  "error",
  "go_away",
  "session_resumption",
  "usage",
]);

function isObject(value: unknown): value is RawMessage {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireObject(value: unknown): RawMessage {
  if (!isObject(value)) {
    throw new Error("服务端消息格式无效");
  }
  return value;
}

export function parseServerMessage(raw: string): ServerMessage {
  const parsed = requireObject(JSON.parse(raw));
  const type = parsed.type;

  if (typeof type !== "string") {
    throw new Error("服务端消息格式无效");
  }

  if (!knownTypes.has(type)) {
    return {
      type: "unknown",
      originalType: type,
      data: parsed.data,
    };
  }

  return parsed as ServerMessage;
}
