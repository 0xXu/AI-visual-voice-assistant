import type { Dispatch } from "react";
import type { SessionAction } from "../app/session-reducer";
import { AudioCapture } from "../media/audio-capture";
import { PcmAudioPlayer } from "../media/pcm-audio-player";
import { VideoFrameSampler } from "../media/video-frame-sampler";
import type { ServerMessage, TerminalStatus } from "../protocol/messages";
import { WebSocketClient } from "../protocol/websocket-client";

export interface SessionOrchestratorOptions {
  wsUrl: string;
  protocolStage: number;
  dispatch: Dispatch<SessionAction>;
}

export interface SessionControls {
  start(stream: MediaStream, video: HTMLVideoElement): void;
  sendText(text: string): void;
  setMuted(muted: boolean): void;
  setVideoPaused(paused: boolean): void;
  stop(): void;
  destroy(): void;
}

const terminalStatuses = new Set<TerminalStatus>([
  "stopped",
  "idle_timeout",
  "max_duration",
  "budget_exceeded",
]);

export class SessionOrchestrator implements SessionControls {
  private client: WebSocketClient | null = null;
  private stream: MediaStream | null = null;
  private video: HTMLVideoElement | null = null;
  private audioCapture: AudioCapture | null = null;
  private videoSampler: VideoFrameSampler | null = null;
  private readonly player = new PcmAudioPlayer();
  private connected = false;
  private muted = false;
  private videoPaused = false;
  private voiceTurnActive = false;

  constructor(private readonly options: SessionOrchestratorOptions) {}

  start(stream: MediaStream, video: HTMLVideoElement): void {
    this.stream = stream;
    this.video = video;

    const client = new WebSocketClient({
      url: this.options.wsUrl,
      onMessage: (message) => this.handleMessage(message),
      onStateChange: (state) => {
        if (state === "open") {
          client.send({ type: "start_session", data: "" });
        } else if (state === "recovering") {
          this.options.dispatch({ type: "SESSION_RECOVERING" });
        } else if (state === "error") {
          this.options.dispatch({
            type: "ERROR_RECEIVED",
            message: "实时连接异常，请稍后重试。",
          });
        } else if (state === "failed") {
          this.connected = false;
          this.stopCapture();
          this.options.dispatch({
            type: "ERROR_RECEIVED",
            message: "连接失败，请检查网络后重新开始。",
          });
        }
      },
    });

    this.client = client;
    client.connect();
  }

  sendText(text: string): void {
    const value = text.trim();
    if (!value) {
      return;
    }
    if (this.client?.send({ type: "text", data: value })) {
      this.options.dispatch({ type: "TEXT_SENT", text: value });
    }
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    this.stream?.getAudioTracks().forEach((track) => {
      track.enabled = !muted;
    });
    this.options.dispatch({ type: "SET_MUTED", muted });
  }

  setVideoPaused(paused: boolean): void {
    this.videoPaused = paused;
    this.stream?.getVideoTracks().forEach((track) => {
      track.enabled = !paused;
    });
    if (paused) {
      this.videoSampler?.stop();
    } else if (this.connected) {
      this.startVideoSampler();
    }
    this.options.dispatch({ type: "SET_VIDEO_PAUSED", paused });
  }

  stop(): void {
    this.stopCapture();
    this.player.clear();
    this.client?.send({ type: "stop_session", data: "" });
    this.options.dispatch({
      type: "SESSION_TERMINATED",
      status: "stopped",
    });
  }

  destroy(): void {
    this.stopCapture();
    this.player.clear();
    this.client?.close();
    this.client = null;
    void this.player.close();
  }

  private handleMessage(message: ServerMessage): void {
    switch (message.type) {
      case "status":
        if (message.data === "connected") {
          this.connected = true;
          this.options.dispatch({ type: "SESSION_CONNECTED" });
          this.startCapture();
        } else if (terminalStatuses.has(message.data)) {
          this.connected = false;
          this.stopCapture();
          this.options.dispatch({
            type: "SESSION_TERMINATED",
            status: message.data,
          });
        }
        break;
      case "text":
        this.options.dispatch({ type: "MODEL_TEXT", text: message.data });
        break;
      case "user_text":
        this.options.dispatch({ type: "USER_TEXT", text: message.data });
        break;
      case "audio":
        this.player.enqueue(message.data);
        this.options.dispatch({ type: "MODEL_AUDIO_STARTED" });
        break;
      case "turn_complete":
        this.voiceTurnActive = false;
        this.options.dispatch({ type: "TURN_COMPLETE" });
        break;
      case "interrupted":
        this.player.clear();
        this.options.dispatch({ type: "MODEL_INTERRUPTED" });
        break;
      case "go_away":
        this.options.dispatch({ type: "SESSION_RECOVERING" });
        break;
      case "usage":
        this.options.dispatch({ type: "USAGE_RECEIVED", usage: message.data });
        break;
      case "error":
        this.options.dispatch({
          type: "ERROR_RECEIVED",
          message: message.data,
        });
        break;
      default:
        break;
    }
  }

  private startCapture(): void {
    if (!this.stream || !this.video) {
      return;
    }

    if (!this.muted) {
      this.audioCapture = new AudioCapture({
        stream: this.stream,
        onChunk: (data) => {
          if (!this.voiceTurnActive) {
            this.voiceTurnActive = true;
            this.options.dispatch({ type: "VOICE_TURN_STARTED" });
          }
          this.client?.send({ type: "audio", data });
        },
      });
      void this.audioCapture.start();
    }

    if (!this.videoPaused) {
      this.startVideoSampler();
    }
  }

  private startVideoSampler(): void {
    if (!this.video) {
      return;
    }

    this.videoSampler?.stop();
    this.videoSampler = new VideoFrameSampler({
      video: this.video,
      getBufferedAmount: () => this.client?.bufferedAmount ?? 0,
      onFrame: (frame) => {
        this.client?.send({ type: "video_frame", ...frame });
      },
    });
    this.videoSampler.start();
  }

  private stopCapture(): void {
    this.audioCapture?.stop();
    this.videoSampler?.stop();
    this.audioCapture = null;
    this.videoSampler = null;
  }
}
