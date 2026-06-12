export interface VideoFrame {
  data: string;
  timestamp: number;
  sequence: number;
}

export interface VideoFrameSamplerOptions {
  video: HTMLVideoElement;
  onFrame: (frame: VideoFrame) => void;
  getBufferedAmount: () => number;
  now?: () => number;
  intervalMs?: number;
}

const maxBufferedAmount = 256 * 1024;
const maxJpegBytes = 512 * 1024;
const maxLongEdge = 960;
const jpegQualities = [0.68, 0.55, 0.42];

export class VideoFrameSampler {
  private readonly canvas = document.createElement("canvas");
  private sequence = 0;
  private timer: number | null = null;

  constructor(private readonly options: VideoFrameSamplerOptions) {}

  start(): void {
    if (this.timer !== null) {
      return;
    }
    this.timer = window.setInterval(
      () => this.captureFrame(),
      this.options.intervalMs ?? 1000,
    );
  }

  stop(): void {
    if (this.timer !== null) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
  }

  nextMetadata() {
    this.sequence += 1;
    return {
      sequence: this.sequence,
      timestamp: (this.options.now ?? Date.now)(),
    };
  }

  shouldSkipFrame(
    bufferedAmount = this.options.getBufferedAmount(),
    visible = document.visibilityState === "visible",
  ): boolean {
    return !visible || bufferedAmount > maxBufferedAmount;
  }

  captureFrame(): void {
    if (
      this.shouldSkipFrame() ||
      this.options.video.videoWidth <= 0 ||
      this.options.video.videoHeight <= 0
    ) {
      return;
    }
    const context = this.canvas.getContext("2d");
    if (!context) {
      return;
    }

    const { width, height } = this.scaledSize(
      this.options.video.videoWidth,
      this.options.video.videoHeight,
    );

    this.canvas.width = width;
    this.canvas.height = height;
    context.drawImage(this.options.video, 0, 0, width, height);

    const data = this.encodeJpeg();
    if (!data) {
      return;
    }

    this.options.onFrame({
      ...this.nextMetadata(),
      data,
    });
  }

  private scaledSize(width: number, height: number) {
    const longEdge = Math.max(width, height);
    if (longEdge <= maxLongEdge) {
      return { width, height };
    }

    const scale = maxLongEdge / longEdge;
    return {
      width: Math.round(width * scale),
      height: Math.round(height * scale),
    };
  }

  private encodeJpeg(): string | null {
    for (const quality of jpegQualities) {
      const dataUrl = this.canvas.toDataURL("image/jpeg", quality);
      const prefix = "data:image/jpeg;base64,";
      if (!dataUrl.startsWith(prefix)) {
        continue;
      }

      const base64 = dataUrl.slice(prefix.length);
      if (this.base64ByteLength(base64) <= maxJpegBytes) {
        return base64;
      }
    }

    return null;
  }

  private base64ByteLength(value: string): number {
    const padding = value.endsWith("==") ? 2 : value.endsWith("=") ? 1 : 0;
    return Math.floor((value.length * 3) / 4) - padding;
  }
}
