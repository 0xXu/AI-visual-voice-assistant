import { pcm16Base64ToFloat32 } from "./audio-codec";

export class PcmAudioPlayer {
  private readonly audioContext: AudioContext;
  private readonly sources = new Set<AudioBufferSourceNode>();
  private nextStartTime: number;

  constructor(sampleRate = 24_000) {
    this.audioContext = new AudioContext({ sampleRate });
    this.nextStartTime = this.audioContext.currentTime;
  }

  enqueue(base64Pcm: string): void {
    const samples = pcm16Base64ToFloat32(base64Pcm);
    const channelSamples = new Float32Array(samples.length);
    const buffer = this.audioContext.createBuffer(
      1,
      samples.length,
      this.audioContext.sampleRate,
    );
    const source = this.audioContext.createBufferSource();
    const startTime = Math.max(
      this.audioContext.currentTime,
      this.nextStartTime,
    );

    channelSamples.set(samples);
    buffer.copyToChannel(channelSamples, 0);
    source.buffer = buffer;
    source.connect(this.audioContext.destination);
    source.addEventListener("ended", () => {
      this.sources.delete(source);
    });

    this.sources.add(source);
    source.start(startTime);
    this.nextStartTime = startTime + buffer.duration;
  }

  clear(): void {
    this.sources.forEach((source) => {
      try {
        source.stop();
      } catch {
        // Already stopped sources are removed by their ended handlers.
      }
    });
    this.sources.clear();
    this.nextStartTime = this.audioContext.currentTime;
  }

  async close(): Promise<void> {
    this.clear();
    await this.audioContext.close();
  }
}
