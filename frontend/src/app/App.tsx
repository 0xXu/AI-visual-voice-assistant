import { useCallback, useEffect, useRef, useState } from "react";
import { DeviceCheckScreen } from "../components/DeviceCheckScreen";
import { EntryScreen } from "../components/EntryScreen";
import { LiveSessionScreen } from "../components/LiveSessionScreen";
import { SessionSummary } from "../components/SessionSummary";
import { TranscriptDrawer } from "../components/TranscriptDrawer";
import {
  type CreateOrchestrator,
  useSession,
} from "../hooks/useSession";
import {
  type DeviceOptions,
  MediaController,
} from "../media/media-controller";

type Screen = "entry" | "device-check" | "live-session" | "summary";

export interface AppProps {
  createOrchestrator?: CreateOrchestrator;
}

function getMediaErrorName(error: unknown) {
  return error instanceof DOMException ? error.name : "UnknownError";
}

export function App({ createOrchestrator }: AppProps = {}) {
  const controllerRef = useRef<MediaController | null>(null);
  const sessionStartedRef = useRef(false);
  const [screen, setScreen] = useState<Screen>("entry");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const {
    state,
    startSession,
    sendText,
    setTranscriptOpen,
    toggleMute,
    toggleVideo,
    stopSession,
    resetSession,
    protocolStage,
  } = useSession(createOrchestrator);

  useEffect(() => {
    return () => {
      controllerRef.current?.stop();
    };
  }, []);

  useEffect(() => {
    if (state.phase !== "ended") {
      return;
    }

    controllerRef.current?.stop();
    setScreen("summary");
  }, [state.phase]);

  const handleVideoReady = useCallback(
    (video: HTMLVideoElement) => {
      if (!stream || sessionStartedRef.current) {
        return;
      }
      sessionStartedRef.current = true;
      startSession(stream, video);
    },
    [startSession, stream],
  );

  const controller = () => {
    controllerRef.current ??= new MediaController();
    return controllerRef.current;
  };

  const openDevices = async (options: DeviceOptions = {}) => {
    setError(null);
    try {
      const mediaController = controller();
      const nextStream = await mediaController.open(options);
      const nextDevices = await mediaController.listDevices();
      setStream(nextStream);
      setDevices(nextDevices);
      setScreen("device-check");
    } catch (nextError) {
      setError(getMediaErrorName(nextError));
      setScreen("device-check");
    }
  };

  const restartSession = () => {
    sessionStartedRef.current = false;
    resetSession();
    setStream(null);
    setDevices([]);
    setError(null);
    void openDevices();
  };

  if (screen === "device-check") {
    return (
      <DeviceCheckScreen
        stream={stream}
        devices={devices}
        error={error}
        onRetry={() => void openDevices()}
        onDeviceChange={(options) => void openDevices(options)}
        onConfirm={() => {
          if (stream) {
            sessionStartedRef.current = false;
            setScreen("live-session");
          }
        }}
      />
    );
  }

  if (screen === "live-session" && stream) {
    return (
      <LiveSessionScreen
        stream={stream}
        state={state}
        onVideoReady={handleVideoReady}
        protocolStage={protocolStage}
        onOpenTranscript={() => setTranscriptOpen(true)}
        onCloseTranscript={() => setTranscriptOpen(false)}
        onSendText={sendText}
        onToggleMute={toggleMute}
        onToggleVideo={toggleVideo}
        onFlipCamera={() => undefined}
        onStop={stopSession}
      />
    );
  }

  if (screen === "summary") {
    return (
      <>
        <SessionSummary
          terminalStatus={state.terminalStatus}
          usage={state.usage}
          messages={state.messages}
          onRestart={restartSession}
          onOpenTranscript={() => setTranscriptOpen(true)}
        />
        <TranscriptDrawer
          open={state.transcriptOpen}
          messages={state.messages}
          protocolStage={protocolStage}
          onClose={() => setTranscriptOpen(false)}
          onSendText={sendText}
        />
      </>
    );
  }

  return <EntryScreen onStart={() => void openDevices()} />;
}
