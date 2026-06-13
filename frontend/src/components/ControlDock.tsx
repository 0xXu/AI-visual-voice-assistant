import {
  Mic,
  MicOff,
  RotateCcw,
  Square,
  Video,
  VideoOff,
} from "lucide-react";

interface ControlDockProps {
  muted: boolean;
  videoPaused: boolean;
  onToggleMute: () => void;
  onToggleVideo: () => void;
  onFlipCamera: () => void;
  onStop: () => void;
}

export function ControlDock({
  muted,
  videoPaused,
  onToggleMute,
  onToggleVideo,
  onFlipCamera,
  onStop,
}: ControlDockProps) {
  return (
    <div className="control-dock" aria-label="会话控制">
      <button
        type="button"
        aria-label={muted ? "取消静音" : "静音"}
        aria-pressed={muted}
        onClick={onToggleMute}
      >
        {muted ? <MicOff size={20} /> : <Mic size={20} />}
      </button>
      <button
        type="button"
        aria-label={videoPaused ? "恢复画面" : "暂停画面"}
        aria-pressed={videoPaused}
        onClick={onToggleVideo}
      >
        {videoPaused ? <VideoOff size={20} /> : <Video size={20} />}
      </button>
      <button type="button" aria-label="翻转镜头" onClick={onFlipCamera}>
        <RotateCcw size={20} />
      </button>
      <button type="button" aria-label="结束会话" onClick={onStop}>
        <Square size={20} />
      </button>
    </div>
  );
}
