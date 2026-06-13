import { useEffect, useMemo, useRef } from "react";
import type { SessionState } from "../app/session-reducer";
import { ControlDock } from "./ControlDock";
import { StatusBadge } from "./StatusBadge";
import { TranscriptDrawer } from "./TranscriptDrawer";

interface LiveSessionScreenProps {
  stream: MediaStream;
  state: SessionState;
  onVideoReady: (video: HTMLVideoElement) => void;
  protocolStage: number;
  onOpenTranscript: () => void;
  onCloseTranscript: () => void;
  onSendText: (text: string) => void;
  onToggleMute: () => void;
  onToggleVideo: () => void;
  onFlipCamera: () => void;
  onStop: () => void;
}

export function LiveSessionScreen({
  stream,
  state,
  onVideoReady,
  protocolStage,
  onOpenTranscript,
  onCloseTranscript,
  onSendText,
  onToggleMute,
  onToggleVideo,
  onFlipCamera,
  onStop,
}: LiveSessionScreenProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const onVideoReadyRef = useRef(onVideoReady);
  const latestMessage = useMemo(
    () => state.messages.at(-1),
    [state.messages],
  );

  useEffect(() => {
    onVideoReadyRef.current = onVideoReady;
  }, [onVideoReady]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }

    video.srcObject = stream;
    onVideoReadyRef.current(video);
  }, [stream]);

  return (
    <main className="live-screen screen-enter">
      <video ref={videoRef} autoPlay muted playsInline />
      <div className="live-gradient" aria-hidden="true" />

      <header className="live-header">
        <StatusBadge phase={state.phase} />
        <div className="live-indicators" aria-label="媒体状态">
          <span>LIVE</span>
          <span>{state.muted ? "麦克风已静音" : "麦克风开启"}</span>
          <span>{state.videoPaused ? "画面已暂停" : "摄像头开启"}</span>
        </div>
      </header>

      <button className="latest-card" type="button" onClick={onOpenTranscript}>
        <span>{latestMessage?.role === "assistant" ? "AI" : "你"}</span>
        {latestMessage?.text || "实时会话已准备好"}
      </button>

      <button
        className="transcript-open-button"
        type="button"
        onClick={onOpenTranscript}
      >
        查看对话记录
      </button>

      <ControlDock
        muted={state.muted}
        videoPaused={state.videoPaused}
        onToggleMute={onToggleMute}
        onToggleVideo={onToggleVideo}
        onFlipCamera={onFlipCamera}
        onStop={onStop}
      />

      <TranscriptDrawer
        open={state.transcriptOpen}
        messages={state.messages}
        protocolStage={protocolStage}
        onClose={onCloseTranscript}
        onSendText={onSendText}
      />
    </main>
  );
}
