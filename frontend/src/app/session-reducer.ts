import type { TerminalStatus, UsageData } from "../protocol/messages";

export type SessionPhase =
  | "idle"
  | "device-check"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "recovering"
  | "ending"
  | "ended";

export interface TranscriptMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  source: "voice" | "text";
  complete: boolean;
}

export interface SessionState {
  phase: SessionPhase;
  messages: TranscriptMessage[];
  terminalStatus: TerminalStatus | null;
  usage: UsageData | null;
  error: string | null;
  muted: boolean;
  videoPaused: boolean;
  transcriptOpen: boolean;
}

export type SessionAction =
  | { type: "OPEN_DEVICE_CHECK" }
  | { type: "SESSION_CONNECTING" }
  | { type: "SESSION_CONNECTED" }
  | { type: "VOICE_TURN_STARTED" }
  | { type: "USER_TEXT"; text: string }
  | { type: "TEXT_SENT"; text: string }
  | { type: "MODEL_TEXT"; text: string }
  | { type: "MODEL_AUDIO_STARTED" }
  | { type: "MODEL_INTERRUPTED" }
  | { type: "TURN_COMPLETE" }
  | { type: "SESSION_RECOVERING" }
  | { type: "SESSION_TERMINATED"; status: TerminalStatus }
  | { type: "USAGE_RECEIVED"; usage: UsageData }
  | { type: "ERROR_RECEIVED"; message: string }
  | { type: "SET_MUTED"; muted: boolean }
  | { type: "SET_VIDEO_PAUSED"; paused: boolean }
  | { type: "SET_TRANSCRIPT_OPEN"; open: boolean }
  | { type: "RESET_SESSION" };

export const initialSessionState: SessionState = {
  phase: "idle",
  messages: [],
  terminalStatus: null,
  usage: null,
  error: null,
  muted: false,
  videoPaused: false,
  transcriptOpen: false,
};

function createMessage(
  state: SessionState,
  role: TranscriptMessage["role"],
  text: string,
  source: TranscriptMessage["source"],
  complete: boolean,
): TranscriptMessage {
  return {
    id: `${role}-${state.messages.length + 1}`,
    role,
    text,
    source,
    complete,
  };
}

function appendAssistantText(
  state: SessionState,
  text: string,
): TranscriptMessage[] {
  const lastMessage = state.messages.at(-1);

  if (lastMessage?.role === "assistant" && !lastMessage.complete) {
    return [
      ...state.messages.slice(0, -1),
      { ...lastMessage, text: `${lastMessage.text}${text}` },
    ];
  }

  return [...state.messages, createMessage(state, "assistant", text, "voice", false)];
}

function startVoiceTurn(state: SessionState): TranscriptMessage[] {
  const lastMessage = state.messages.at(-1);

  if (lastMessage?.role === "user" && !lastMessage.complete) {
    return state.messages;
  }

  return [
    ...state.messages,
    createMessage(state, "user", "语音提问", "voice", false),
  ];
}

function appendUserVoiceText(
  state: SessionState,
  text: string,
): TranscriptMessage[] {
  const lastMessage = state.messages.at(-1);

  if (lastMessage?.role === "user" && !lastMessage.complete) {
    const nextText =
      lastMessage.text === "语音提问" ? text : `${lastMessage.text}${text}`;
    return [...state.messages.slice(0, -1), { ...lastMessage, text: nextText }];
  }

  return [...state.messages, createMessage(state, "user", text, "voice", false)];
}

export function sessionReducer(
  state: SessionState,
  action: SessionAction,
): SessionState {
  switch (action.type) {
    case "OPEN_DEVICE_CHECK":
      return { ...state, phase: "device-check", error: null };
    case "SESSION_CONNECTING":
      return { ...state, phase: "connecting", error: null };
    case "SESSION_CONNECTED":
      return { ...state, phase: "listening", error: null };
    case "VOICE_TURN_STARTED":
      return {
        ...state,
        phase: "listening",
        messages: startVoiceTurn(state),
      };
    case "USER_TEXT":
      return {
        ...state,
        messages: appendUserVoiceText(state, action.text),
      };
    case "TEXT_SENT":
      return {
        ...state,
        phase: "thinking",
        messages: [
          ...state.messages,
          createMessage(state, "user", action.text, "text", true),
        ],
      };
    case "MODEL_TEXT":
      return {
        ...state,
        phase: "speaking",
        messages: appendAssistantText(state, action.text),
      };
    case "MODEL_AUDIO_STARTED":
      return { ...state, phase: "speaking" };
    case "MODEL_INTERRUPTED":
      return { ...state, phase: "listening" };
    case "TURN_COMPLETE":
      return {
        ...state,
        phase: "listening",
        messages: state.messages.map((message, index) =>
          index === state.messages.length - 1 && message.role === "assistant"
            ? { ...message, complete: true }
            : message,
        ),
      };
    case "SESSION_RECOVERING":
      return { ...state, phase: "recovering" };
    case "SESSION_TERMINATED":
      return {
        ...state,
        phase: "ending",
        terminalStatus: action.status,
      };
    case "USAGE_RECEIVED":
      return {
        ...state,
        phase: state.phase === "ending" ? "ended" : state.phase,
        usage: state.phase === "ending" ? action.usage : state.usage,
      };
    case "ERROR_RECEIVED":
      return { ...state, error: action.message };
    case "SET_MUTED":
      return { ...state, muted: action.muted };
    case "SET_VIDEO_PAUSED":
      return { ...state, videoPaused: action.paused };
    case "SET_TRANSCRIPT_OPEN":
      return { ...state, transcriptOpen: action.open };
    case "RESET_SESSION":
      return initialSessionState;
    default:
      return state;
  }
}
