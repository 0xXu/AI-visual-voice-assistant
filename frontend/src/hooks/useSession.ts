import { useEffect, useReducer, useRef } from "react";
import {
  initialSessionState,
  sessionReducer,
} from "../app/session-reducer";
import {
  SessionOrchestrator,
  type SessionControls,
  type SessionOrchestratorOptions,
} from "../session/session-orchestrator";

export type CreateOrchestrator = (
  options: SessionOrchestratorOptions,
) => SessionControls;

const defaultWsUrl = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";
const defaultProtocolStage = Number(import.meta.env.VITE_PROTOCOL_STAGE ?? 8);

export function useSession(createOrchestrator?: CreateOrchestrator) {
  const [state, dispatch] = useReducer(sessionReducer, initialSessionState);
  const orchestratorRef = useRef<SessionControls | null>(null);

  const getOrchestrator = () => {
    orchestratorRef.current ??= (
      createOrchestrator ??
      ((options) => new SessionOrchestrator(options))
    )({
      wsUrl: defaultWsUrl,
      protocolStage: defaultProtocolStage,
      dispatch,
    });
    return orchestratorRef.current;
  };

  useEffect(() => {
    return () => {
      orchestratorRef.current?.destroy();
    };
  }, []);

  return {
    state,
    startSession: (stream: MediaStream, video: HTMLVideoElement) => {
      dispatch({ type: "SESSION_CONNECTING" });
      getOrchestrator().start(stream, video);
    },
    sendText: (text: string) => {
      getOrchestrator().sendText(text);
    },
    setTranscriptOpen: (open: boolean) => {
      dispatch({ type: "SET_TRANSCRIPT_OPEN", open });
    },
    toggleMute: () => {
      getOrchestrator().setMuted(!state.muted);
    },
    toggleVideo: () => {
      getOrchestrator().setVideoPaused(!state.videoPaused);
    },
    stopSession: () => {
      getOrchestrator().stop();
    },
    resetSession: () => {
      dispatch({ type: "RESET_SESSION" });
    },
    protocolStage: defaultProtocolStage,
  };
}
