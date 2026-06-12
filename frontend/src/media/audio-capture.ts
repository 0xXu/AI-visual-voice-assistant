import { floatToPcm16, pcm16ToBase64, resampleLinear } from "./audio-codec";

interface AudioCaptureOptions {
  stream: MediaStream;
  onChunk: (base64Pcm: string) => void;
  targetSampleRate?: number;
  chunkSamples?: number;
}

export class AudioCapture {
  private audioContext: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private pendingSamples: number[] = [];

  constructor(private readonly options: AudioCaptureOptions) {}

  async start(): Promise<void> {
    if (this.audioContext) {
      return;
    }

    const audioContext = new AudioContext();
    await audioContext.audioWorklet.addModule("/audio-capture.worklet.js");

    const source = audioContext.createMediaStreamSource(this.options.stream);
    const worklet = new AudioWorkletNode(
      audioContext,
      "audio-capture-processor",
    );

    worklet.port.onmessage = (event: MessageEvent<Float32Array>) => {
      this.handleSamples(event.data, audioContext.sampleRate);
    };

    source.connect(worklet);
    worklet.connect(audioContext.destination);

    this.audioContext = audioContext;
    this.source = source;
    this.worklet = worklet;
  }

  stop(): void {
    this.worklet?.disconnect();
    this.source?.disconnect();
    this.worklet = null;
    this.source = null;
    this.pendingSamples = [];

    const audioContext = this.audioContext;
    this.audioContext = null;
    void audioContext?.close();
  }

  private handleSamples(samples: Float32Array, sourceRate: number): void {
    const targetRate = this.options.targetSampleRate ?? 16_000;
    const chunkSamples = this.options.chunkSamples ?? 640;
    const resampled = resampleLinear(samples, sourceRate, targetRate);

    resampled.forEach((sample) => {
      this.pendingSamples.push(sample);
    });

    while (this.pendingSamples.length >= chunkSamples) {
      const chunk = new Float32Array(this.pendingSamples.splice(0, chunkSamples));
      this.options.onChunk(pcm16ToBase64(floatToPcm16(chunk)));
    }
  }
}
