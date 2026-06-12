class AudioCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    this.port.postMessage(input.slice());
    return true;
  }
}

registerProcessor("audio-capture-processor", AudioCaptureProcessor);
