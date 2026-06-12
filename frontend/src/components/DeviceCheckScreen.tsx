import { useEffect, useMemo, useRef, useState } from "react";
import { Camera, Mic, RotateCcw } from "lucide-react";
import type { DeviceOptions } from "../media/media-controller";

interface DeviceCheckScreenProps {
  stream: MediaStream | null;
  devices: MediaDeviceInfo[];
  error: string | null;
  onRetry: () => void;
  onDeviceChange: (options: DeviceOptions) => void;
  onConfirm: () => void;
}

const mediaErrorText: Record<string, string> = {
  NotAllowedError:
    "未获得摄像头或麦克风权限，请在浏览器地址栏中允许访问。",
  NotFoundError: "未检测到可用的摄像头或麦克风。",
  NotReadableError:
    "设备正被其他应用占用，请关闭占用设备的应用后重试。",
};

function mapMediaError(error: string | null) {
  if (!error) return null;
  return mediaErrorText[error] ?? "无法打开摄像头或麦克风，请检查设备后重试。";
}

export function DeviceCheckScreen({
  stream,
  devices,
  error,
  onRetry,
  onDeviceChange,
  onConfirm,
}: DeviceCheckScreenProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [audioDeviceId, setAudioDeviceId] = useState("");
  const [videoDeviceId, setVideoDeviceId] = useState("");
  const [level, setLevel] = useState(0);

  const videoDevices = useMemo(
    () => devices.filter((device) => device.kind === "videoinput"),
    [devices],
  );
  const audioDevices = useMemo(
    () => devices.filter((device) => device.kind === "audioinput"),
    [devices],
  );
  const mappedError = mapMediaError(error);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  useEffect(() => {
    const AudioContextConstructor = window.AudioContext;
    const audioTrack = stream?.getAudioTracks()[0];

    if (!stream || !AudioContextConstructor || !audioTrack) {
      setLevel(0);
      return;
    }

    const audioContext = new AudioContextConstructor();
    const analyser = audioContext.createAnalyser();
    const source = audioContext.createMediaStreamSource(stream);
    const samples = new Uint8Array(analyser.frequencyBinCount);
    let frame = 0;

    analyser.fftSize = 256;
    source.connect(analyser);

    const tick = () => {
      analyser.getByteFrequencyData(samples);
      const average =
        samples.reduce((total, sample) => total + sample, 0) / samples.length;
      setLevel(Math.min(100, Math.round((average / 255) * 100)));
      frame = window.requestAnimationFrame(tick);
    };

    frame = window.requestAnimationFrame(tick);

    return () => {
      window.cancelAnimationFrame(frame);
      source.disconnect();
      void audioContext.close();
    };
  }, [stream]);

  const handleVideoChange = (nextVideoDeviceId: string) => {
    setVideoDeviceId(nextVideoDeviceId);
    onDeviceChange({ audioDeviceId, videoDeviceId: nextVideoDeviceId });
  };

  const handleAudioChange = (nextAudioDeviceId: string) => {
    setAudioDeviceId(nextAudioDeviceId);
    onDeviceChange({ audioDeviceId: nextAudioDeviceId, videoDeviceId });
  };

  return (
    <main className="device-screen screen-enter">
      <section className="device-preview" aria-label="摄像头预览">
        {stream ? (
          <video ref={videoRef} autoPlay muted playsInline />
        ) : (
          <div className="device-preview__empty">等待设备授权</div>
        )}
        <div className="device-preview__shade" aria-hidden="true" />
      </section>

      <section className="device-panel" aria-labelledby="device-title">
        <p className="eyebrow">
          <span className="eyebrow__icon" aria-hidden="true">
            <Camera size={14} strokeWidth={2} />
          </span>
          设备检测
        </p>
        <h1 id="device-title">检查摄像头与麦克风</h1>
        <p className="device-panel__copy">
          确认画面和声音输入正常后，再开始云端实时会话。
        </p>

        {mappedError ? (
          <div className="device-error" role="alert">
            <p>{mappedError}</p>
            <button className="button-secondary" type="button" onClick={onRetry}>
              <RotateCcw size={16} aria-hidden="true" />
              重新检测
            </button>
          </div>
        ) : null}

        <div className="device-controls">
          <label>
            <span>
              <Camera size={16} aria-hidden="true" />
              摄像头
            </span>
            <select
              value={videoDeviceId}
              onChange={(event) => handleVideoChange(event.target.value)}
            >
              <option value="">默认摄像头</option>
              {videoDevices.map((device, index) => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label || `摄像头 ${index + 1}`}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>
              <Mic size={16} aria-hidden="true" />
              麦克风
            </span>
            <select
              value={audioDeviceId}
              onChange={(event) => handleAudioChange(event.target.value)}
            >
              <option value="">默认麦克风</option>
              {audioDevices.map((device, index) => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label || `麦克风 ${index + 1}`}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="audio-meter" aria-label="麦克风电平">
          <span style={{ inlineSize: `${level}%` }} />
        </div>

        <button className="button-primary" type="button" onClick={onConfirm}>
          开始会话
        </button>
      </section>
    </main>
  );
}
