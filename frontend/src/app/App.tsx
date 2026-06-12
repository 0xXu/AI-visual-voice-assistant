import { useEffect, useRef, useState } from "react";
import { DeviceCheckScreen } from "../components/DeviceCheckScreen";
import { EntryScreen } from "../components/EntryScreen";
import {
  type DeviceOptions,
  MediaController,
} from "../media/media-controller";

type Screen = "entry" | "device-check";

function getMediaErrorName(error: unknown) {
  return error instanceof DOMException ? error.name : "UnknownError";
}

export function App() {
  const controllerRef = useRef<MediaController | null>(null);
  const [screen, setScreen] = useState<Screen>("entry");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.stop();
    };
  }, []);

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

  if (screen === "device-check") {
    return (
      <DeviceCheckScreen
        stream={stream}
        devices={devices}
        error={error}
        onRetry={() => void openDevices()}
        onDeviceChange={(options) => void openDevices(options)}
        onConfirm={() => undefined}
      />
    );
  }

  return <EntryScreen onStart={() => void openDevices()} />;
}
