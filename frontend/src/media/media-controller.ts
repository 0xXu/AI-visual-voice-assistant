export interface DeviceOptions {
  audioDeviceId?: string;
  videoDeviceId?: string;
  facingMode?: "user" | "environment";
}

export class MediaController {
  private stream: MediaStream | null = null;

  async open(options: DeviceOptions = {}): Promise<MediaStream> {
    this.stop();
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: options.audioDeviceId
        ? { deviceId: { exact: options.audioDeviceId } }
        : true,
      video: options.videoDeviceId
        ? { deviceId: { exact: options.videoDeviceId } }
        : { facingMode: options.facingMode ?? "user" },
    });
    return this.stream;
  }

  async listDevices(): Promise<MediaDeviceInfo[]> {
    return navigator.mediaDevices.enumerateDevices();
  }

  setAudioEnabled(enabled: boolean): void {
    this.stream?.getAudioTracks().forEach((track) => {
      track.enabled = enabled;
    });
  }

  setVideoEnabled(enabled: boolean): void {
    this.stream?.getVideoTracks().forEach((track) => {
      track.enabled = enabled;
    });
  }

  stop(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }
}
