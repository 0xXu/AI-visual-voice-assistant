# AI 视觉对话助手前端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一个与现有 Python 后端完全解耦的 Vite + React 前端，让用户在设备检测后通过摄像头、麦克风和文字与 Gemini Live 进行实时视觉对话。

**Architecture:** 前端位于独立的 `frontend/` 应用目录，只依赖 `docs/frontend-integration-contract.md`。React UI 通过 reducer 和 Session Orchestrator 驱动独立的 WebSocket、媒体采集、视频抽帧与 PCM 播放控制器；后端先用一个小 PR 增加用户输入转写事件。

**Tech Stack:** Python 3.11、FastAPI、google-genai、pytest、Vite、React、TypeScript、Vitest、Testing Library、Lucide React、原生 WebSocket、MediaDevices、AudioWorklet、Web Audio、Canvas。

---

## 实施约束

- 本计划共 9 个 PR，每个 PR 只交付一项能力。
- PR 标题不得包含 `Task`、序号前缀或内部计划术语。
- 每个 PR 从最新 `main` 创建 `codex/` 分支；前一个 PR 合并后再创建下一个。
- 每个 PR 合并后，后端测试可运行，前端至少能通过 `npm run build`。
- 测试保持轻量：只覆盖协议、状态机、媒体转换和一条关键 UI 流程。
- 不提交 `.superpowers/`、真实 API Key、浏览器录音或摄像头截图。
- 前端不导入任何 `backend/` Python 文件，也不包含 Gemini API Key。

## 文件结构

```text
frontend/
├── .env.example
├── index.html
├── package.json
├── package-lock.json
├── tsconfig.json
├── vite.config.ts
├── vitest.setup.ts
├── public/
│   └── audio-capture.worklet.js
└── src/
    ├── app/
    │   ├── App.tsx
    │   ├── App.test.tsx
    │   ├── session-reducer.ts
    │   └── session-reducer.test.ts
    ├── components/
    │   ├── EntryScreen.tsx
    │   ├── DeviceCheckScreen.tsx
    │   ├── LiveSessionScreen.tsx
    │   ├── SessionSummary.tsx
    │   ├── TranscriptDrawer.tsx
    │   ├── StatusBadge.tsx
    │   └── ControlDock.tsx
    ├── hooks/
    │   └── useSession.ts
    ├── media/
    │   ├── media-controller.ts
    │   ├── audio-capture.ts
    │   ├── audio-codec.ts
    │   ├── audio-codec.test.ts
    │   ├── pcm-audio-player.ts
    │   ├── video-frame-sampler.ts
    │   └── video-frame-sampler.test.ts
    ├── protocol/
    │   ├── messages.ts
    │   ├── messages.test.ts
    │   └── websocket-client.ts
    ├── session/
    │   └── session-orchestrator.ts
    ├── styles/
    │   ├── tokens.css
    │   ├── globals.css
    │   └── components.css
    ├── main.tsx
    └── vite-env.d.ts
```

---

## PR 1：转发 Gemini 用户语音转写

**单一功能:** 后端把 Gemini Live 的输入音频转写作为 `user_text` 服务端事件发送给前端。

**分支:** `codex/user-audio-transcription`

**Files:**

- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `docs/frontend-integration-contract.md`

- [ ] **Step 1: 添加输入转写失败测试**

在 `backend/tests/test_gemini_service.py` 添加：

```python
def test_maps_input_audio_transcription_to_user_text():
    message = types.LiveServerMessage(
        server_content=types.LiveServerContent(
            input_transcription=types.Transcription(text="桌上这个是什么？")
        )
    )

    class ReceivingSession:
        async def receive(self):
            yield message

    async def collect():
        return [
            event
            async for event in GeminiSession(ReceivingSession()).receive()
        ]

    assert asyncio.run(collect()) == [
        GeminiResponse(
            payload={
                "type": "user_text",
                "data": "桌上这个是什么？",
            }
        )
    ]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend
uv run pytest tests/test_gemini_service.py::test_maps_input_audio_transcription_to_user_text -q
```

Expected: FAIL，收集结果为空。

- [ ] **Step 3: 转发非空输入转写**

在 `GeminiSession.receive()` 的 `if server_content:` 块中、输出转写处理之前加入：

```python
input_transcription = getattr(
    server_content,
    "input_transcription",
    None,
)
if input_transcription and input_transcription.text:
    yield GeminiResponse(
        payload={
            "type": "user_text",
            "data": input_transcription.text,
        }
    )
```

- [ ] **Step 4: 更新协议阶段**

在 `docs/frontend-integration-contract.md`：

1. 增加阶段 8：

```markdown
| 8 | Released: user input audio transcription |
```

2. 在服务端文本事件之后增加：

````markdown
### Stage 8 Server User Text

```json
{"type":"user_text","data":"用户语音转写文本"}
```

`data` is Gemini Live input audio transcription. Append non-empty fragments
to the current user voice turn. Deployments below protocol stage 8 do not
send this event; the frontend must remain usable without it.
````

- [ ] **Step 5: 运行后端轻量验证**

Run:

```bash
cd backend
uv run pytest tests/test_gemini_service.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/gemini_service.py \
  backend/tests/test_gemini_service.py \
  docs/frontend-integration-contract.md
git commit -m "feat: 转发用户语音转写"
```

**PR 标题:** `转发 Gemini 用户语音转写`

**功能描述:** 将 Gemini Live 输入音频转写发送为 `user_text` 事件，供前端构建完整问答记录；旧协议部署仍可正常运行。

**实现思路:** 复用已启用的 `input_audio_transcription`，只转发非空文本，并将协议阶段提升到 8。

**测试方式:** `cd backend && uv run pytest tests/test_gemini_service.py -q`

---

## PR 2：创建可运行的前端应用骨架

**单一功能:** 创建独立 Vite React 应用并实现深海科技入口屏。

**分支:** `codex/frontend-shell`

**Files:**

- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/vitest.setup.ts`
- Create: `frontend/index.html`
- Create: `frontend/.env.example`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/vite-env.d.ts`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/App.test.tsx`
- Create: `frontend/src/components/EntryScreen.tsx`
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/globals.css`
- Create: `frontend/src/styles/components.css`
- Modify: `.gitignore`

- [ ] **Step 1: 初始化依赖**

Run:

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install lucide-react
npm install -D vitest jsdom @testing-library/react @testing-library/jest-dom
```

Expected: 生成 `package-lock.json`，安装无错误。

- [ ] **Step 2: 配置脚本和测试环境**

将 `frontend/package.json` scripts 设为：

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

在 `frontend/vite.config.ts` 使用：

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./vitest.setup.ts",
  },
});
```

在 `frontend/vitest.setup.ts` 使用：

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 3: 先写入口屏测试**

`frontend/src/app/App.test.tsx`：

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("首次加载只显示入口且不请求媒体权限", () => {
    const getUserMedia = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });

    render(<App />);

    expect(
      screen.getByRole("button", { name: "开始视觉对话" }),
    ).toBeInTheDocument();
    expect(getUserMedia).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 4: 实现最小入口屏**

`frontend/src/app/App.tsx`：

```tsx
import { EntryScreen } from "../components/EntryScreen";

export function App() {
  return <EntryScreen onStart={() => undefined} />;
}
```

`frontend/src/components/EntryScreen.tsx`：

```tsx
import { Camera, Mic } from "lucide-react";

interface EntryScreenProps {
  onStart: () => void;
}

export function EntryScreen({ onStart }: EntryScreenProps) {
  return (
    <main className="entry-screen screen-enter">
      <div className="atmosphere" aria-hidden="true" />
      <section className="entry-content">
        <p className="eyebrow">实时视觉对话</p>
        <h1>
          让 AI <span>看见你所看见的</span>
        </h1>
        <p className="entry-description">
          打开摄像头和麦克风，直接询问眼前的物品、环境与操作步骤。
        </p>
        <button className="button-primary" type="button" onClick={onStart}>
          开始视觉对话
        </button>
        <p className="privacy-note">
          <Camera size={16} /> <Mic size={16} />
          设备内容仅在会话期间用于实时回答。
        </p>
      </section>
    </main>
  );
}
```

- [ ] **Step 5: 落地设计变量**

将 `DESIGN.md` 第 2、3、5、7、9 节的变量、基础排版、入口动画和 reduced-motion 规则分别写入：

- `frontend/src/styles/tokens.css`
- `frontend/src/styles/globals.css`
- `frontend/src/styles/components.css`

`frontend/src/main.tsx` 必须导入三个样式文件：

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./app/App";
import "./styles/tokens.css";
import "./styles/globals.css";
import "./styles/components.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 6: 配置环境变量**

`frontend/.env.example`：

```env
VITE_WS_URL=ws://localhost:8000/ws
VITE_PROTOCOL_STAGE=8
```

在根 `.gitignore` 增加：

```gitignore
frontend/node_modules/
frontend/dist/
frontend/.env
```

- [ ] **Step 7: 验证并提交**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected: 1 个测试通过，构建成功。

```bash
git add .gitignore frontend
git commit -m "feat: 创建视觉对话前端入口"
```

**PR 标题:** `创建视觉对话前端入口`

**功能描述:** 新增独立 Vite React 前端，提供深海科技入口页；页面加载不会请求摄像头或麦克风权限。

**实现思路:** 使用 React + TypeScript 和原生 CSS 变量实现，前端通过环境变量配置 WebSocket 地址和协议阶段。

**测试方式:** `cd frontend && npm test && npm run build`

---

## PR 3：增加摄像头与麦克风设备检测

**单一功能:** 用户点击开始后可以授权、预览并选择摄像头和麦克风。

**分支:** `codex/device-check`

**Files:**

- Create: `frontend/src/media/media-controller.ts`
- Create: `frontend/src/components/DeviceCheckScreen.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/App.test.tsx`
- Modify: `frontend/src/styles/components.css`

- [ ] **Step 1: 写入口到设备检测的失败测试**

在 `App.test.tsx` 添加：

```tsx
import { fireEvent } from "@testing-library/react";

it("点击开始后请求设备并显示检测页面", async () => {
  const stream = {
    getTracks: () => [],
    getAudioTracks: () => [{ enabled: true }],
    getVideoTracks: () => [{ enabled: true }],
  } as unknown as MediaStream;
  const getUserMedia = vi.fn().mockResolvedValue(stream);
  const enumerateDevices = vi.fn().mockResolvedValue([
    { deviceId: "cam-1", kind: "videoinput", label: "前置摄像头" },
    { deviceId: "mic-1", kind: "audioinput", label: "内置麦克风" },
  ]);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia, enumerateDevices },
  });

  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "开始视觉对话" }));

  expect(await screen.findByText("检查摄像头与麦克风")).toBeInTheDocument();
  expect(getUserMedia).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: 实现媒体控制器**

`frontend/src/media/media-controller.ts`：

```ts
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
```

- [ ] **Step 3: 实现检测页面**

`DeviceCheckScreen` props：

```ts
interface DeviceCheckScreenProps {
  stream: MediaStream;
  devices: MediaDeviceInfo[];
  error: string | null;
  onRetry: () => void;
  onDeviceChange: (options: DeviceOptions) => void;
  onConfirm: () => void;
}
```

页面必须包含：

- 标题“检查摄像头与麦克风”。
- `<video autoPlay muted playsInline>`，在 effect 中设置 `srcObject = stream`。
- 一个摄像头 `<select>` 和一个麦克风 `<select>`。
- Web Audio `AnalyserNode` 驱动的简单电平条。
- 权限错误中文映射：

```ts
const mediaErrorText: Record<string, string> = {
  NotAllowedError: "未获得摄像头或麦克风权限，请在浏览器地址栏中允许访问。",
  NotFoundError: "未检测到可用的摄像头或麦克风。",
  NotReadableError: "设备正被其他应用占用，请关闭占用设备的应用后重试。",
};
```

- [ ] **Step 4: 在 App 中接入页面阶段**

使用：

```ts
type Screen = "entry" | "device-check";
```

点击入口时创建 `MediaController`、调用 `open()`、授权后 `listDevices()`，成功进入 `device-check`。组件卸载时调用 `stop()`。

- [ ] **Step 5: 验证并提交**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected: 测试通过，构建成功。

```bash
git add frontend/src
git commit -m "feat: 增加音视频设备检测"
```

**PR 标题:** `增加摄像头与麦克风设备检测`

**功能描述:** 用户可在开始会话前预览摄像头、查看麦克风电平并选择输入设备；权限错误提供中文恢复步骤。

**实现思路:** 使用 MediaDevices 和 Web Audio Analyser，权限成功后再枚举设备标签。

**测试方式:** `cd frontend && npm test && npm run build`

---

## PR 4：实现 WebSocket 协议与会话状态机

**单一功能:** 前端能够安全解析后端事件，并按协议驱动会话状态。

**分支:** `codex/session-protocol`

**Files:**

- Create: `frontend/src/protocol/messages.ts`
- Create: `frontend/src/protocol/messages.test.ts`
- Create: `frontend/src/protocol/websocket-client.ts`
- Create: `frontend/src/app/session-reducer.ts`
- Create: `frontend/src/app/session-reducer.test.ts`

- [ ] **Step 1: 定义协议类型**

`frontend/src/protocol/messages.ts`：

```ts
export type TerminalStatus =
  | "stopped"
  | "idle_timeout"
  | "max_duration"
  | "budget_exceeded";

export interface UsageData {
  audio_bytes: number;
  text_chars: number;
  video_frames: number;
  video_replaced_frames: number;
  video_bytes: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  duration_ms: number;
  first_response_latency_ms: number | null;
}

export type ServerMessage =
  | { type: "status"; data: "connected" | TerminalStatus }
  | { type: "text"; data: string }
  | { type: "user_text"; data: string }
  | { type: "audio"; data: string }
  | { type: "turn_complete"; data: "" }
  | { type: "interrupted"; data: "" }
  | { type: "ping"; data: "" }
  | { type: "pong"; data: "" }
  | { type: "error"; data: string }
  | { type: "go_away"; data: { time_left_ms: number } }
  | { type: "session_resumption"; data: { resumable: boolean } }
  | { type: "usage"; data: UsageData }
  | { type: "unknown"; originalType: string; data: unknown };

export type ClientMessage =
  | { type: "start_session"; data: "" }
  | { type: "stop_session"; data: "" }
  | { type: "ping"; data: "" }
  | { type: "pong"; data: "" }
  | { type: "text"; data: string }
  | { type: "audio"; data: string }
  | {
      type: "video_frame";
      data: string;
      timestamp: number;
      sequence: number;
    };
```

实现 `parseServerMessage(raw: string): ServerMessage`，要求 JSON 不是对象时抛出 `Error("服务端消息格式无效")`；未知 `type` 返回 `unknown`。

- [ ] **Step 2: 写协议解析测试**

覆盖：

```ts
expect(parseServerMessage('{"type":"status","data":"connected"}')).toEqual({
  type: "status",
  data: "connected",
});

expect(parseServerMessage('{"type":"future","data":1}')).toEqual({
  type: "unknown",
  originalType: "future",
  data: 1,
});
```

- [ ] **Step 3: 实现 WebSocketClient**

核心接口：

```ts
export interface WebSocketClientOptions {
  url: string;
  onMessage: (message: ServerMessage) => void;
  onStateChange: (
    state: "connecting" | "open" | "closed" | "error",
  ) => void;
}

export class WebSocketClient {
  private socket: WebSocket | null = null;

  constructor(private readonly options: WebSocketClientOptions) {}

  connect(): void {
    if (
      this.socket?.readyState === WebSocket.OPEN ||
      this.socket?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    this.options.onStateChange("connecting");
    const socket = new WebSocket(this.options.url);
    this.socket = socket;

    socket.addEventListener("open", () => {
      this.options.onStateChange("open");
    });
    socket.addEventListener("message", (event) => {
      try {
        const message = parseServerMessage(String(event.data));
        if (message.type === "ping") {
          this.send({ type: "pong", data: "" });
        }
        this.options.onMessage(message);
      } catch {
        this.options.onStateChange("error");
      }
    });
    socket.addEventListener("error", () => {
      this.options.onStateChange("error");
    });
    socket.addEventListener("close", () => {
      if (this.socket === socket) {
        this.socket = null;
      }
      this.options.onStateChange("closed");
    });
  }

  send(message: ClientMessage): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) {
      return false;
    }
    this.socket.send(JSON.stringify(message));
    return true;
  }

  get bufferedAmount(): number { return this.socket?.bufferedAmount ?? 0; }

  close(): void {
    const socket = this.socket;
    this.socket = null;
    if (
      socket?.readyState === WebSocket.OPEN ||
      socket?.readyState === WebSocket.CONNECTING
    ) {
      socket.close(1000, "客户端结束连接");
    }
  }
}
```

收到 `ping` 时自动发送 `{ type: "pong", data: "" }`，同时继续把 `ping` 分发给 reducer。

- [ ] **Step 4: 写 reducer 测试**

关键断言：

```ts
expect(sessionReducer(initialSessionState, { type: "SESSION_CONNECTED" }).phase)
  .toBe("listening");

expect(
  sessionReducer(
    { ...initialSessionState, phase: "speaking" },
    { type: "MODEL_INTERRUPTED" },
  ).phase,
).toBe("listening");

const stopped = sessionReducer(initialSessionState, {
  type: "SESSION_TERMINATED",
  status: "max_duration",
});
expect(stopped.phase).toBe("ending");
expect(stopped.terminalStatus).toBe("max_duration");
```

- [ ] **Step 5: 实现 reducer**

状态必须包含：

```ts
export type SessionPhase =
  | "idle"
  | "device-check"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "recovering"
  | "ending"
  | "ended";

export interface TranscriptMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  source: "voice" | "text";
  complete: boolean;
}

export interface SessionState {
  phase: SessionPhase;
  messages: TranscriptMessage[];
  terminalStatus: TerminalStatus | null;
  usage: UsageData | null;
  error: string | null;
  muted: boolean;
  videoPaused: boolean;
  transcriptOpen: boolean;
}

export type SessionAction =
  | { type: "OPEN_DEVICE_CHECK" }
  | { type: "SESSION_CONNECTING" }
  | { type: "SESSION_CONNECTED" }
  | { type: "VOICE_TURN_STARTED" }
  | { type: "USER_TEXT"; text: string }
  | { type: "TEXT_SENT"; text: string }
  | { type: "MODEL_TEXT"; text: string }
  | { type: "MODEL_AUDIO_STARTED" }
  | { type: "MODEL_INTERRUPTED" }
  | { type: "TURN_COMPLETE" }
  | { type: "SESSION_RECOVERING" }
  | { type: "SESSION_TERMINATED"; status: TerminalStatus }
  | { type: "USAGE_RECEIVED"; usage: UsageData }
  | { type: "ERROR_RECEIVED"; message: string }
  | { type: "SET_MUTED"; muted: boolean }
  | { type: "SET_VIDEO_PAUSED"; paused: boolean }
  | { type: "SET_TRANSCRIPT_OPEN"; open: boolean }
  | { type: "RESET_SESSION" };

export const initialSessionState: SessionState = {
  phase: "idle",
  messages: [],
  terminalStatus: null,
  usage: null,
  error: null,
  muted: false,
  videoPaused: false,
  transcriptOpen: false,
};
```

`usage` 只有在 `phase === "ending"` 时将阶段推进到 `ended`。`user_text` 在协议阶段低于 8 时不会出现，reducer 不依赖它完成会话。

- [ ] **Step 6: 验证并提交**

Run:

```bash
cd frontend
npm test
npm run build
```

```bash
git add frontend/src/protocol frontend/src/app/session-reducer*
git commit -m "feat: 实现实时会话协议状态机"
```

**PR 标题:** `实现实时会话协议状态机`

**功能描述:** 为所有已发布后端事件建立强类型解析和状态转换，未知事件不会导致页面崩溃。

**实现思路:** 原生 WebSocket 负责连接和心跳，纯 reducer 负责可测试的会话状态变化。

**测试方式:** `cd frontend && npm test && npm run build`

---

## PR 5：实现实时音频采集与播放

**单一功能:** 发送 16 kHz PCM16 麦克风音频，并播放 24 kHz PCM16 AI 音频。

**分支:** `codex/live-audio`

**Files:**

- Create: `frontend/public/audio-capture.worklet.js`
- Create: `frontend/src/media/audio-codec.ts`
- Create: `frontend/src/media/audio-codec.test.ts`
- Create: `frontend/src/media/audio-capture.ts`
- Create: `frontend/src/media/pcm-audio-player.ts`

- [ ] **Step 1: 写 PCM 转换测试**

`audio-codec.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import { floatToPcm16, pcm16Base64ToFloat32 } from "./audio-codec";

describe("audio codec", () => {
  it("把浮点采样限制并转换为 PCM16", () => {
    expect(Array.from(floatToPcm16(new Float32Array([-2, -1, 0, 1, 2]))))
      .toEqual([-32768, -32768, 0, 32767, 32767]);
  });

  it("解码小端 PCM16 Base64", () => {
    expect(Array.from(pcm16Base64ToFloat32("AACA/w==")))
      .toEqual([0, -0.00390625]);
  });
});
```

- [ ] **Step 2: 实现编码工具**

`audio-codec.ts` 导出：

```ts
export function floatToPcm16(samples: Float32Array): Int16Array;
export function bytesToBase64(bytes: Uint8Array): string;
export function base64ToBytes(value: string): Uint8Array;
export function pcm16Base64ToFloat32(value: string): Float32Array;
```

转换必须使用小端字节序；编码前将样本限制在 `[-1, 1]`。

- [ ] **Step 3: 实现 AudioWorklet**

`audio-capture.worklet.js`：

```js
class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.targetSamples = 640; // 40 ms at 16 kHz
  }

  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    this.port.postMessage(input.slice());
    return true;
  }
}

registerProcessor("audio-capture-processor", AudioCaptureProcessor);
```

主线程 `AudioCapture`：

- 创建 `AudioContext`。
- `audioWorklet.addModule("/audio-capture.worklet.js")`。
- 将麦克风采样线性重采样为 16 kHz。
- 聚合成 320–640 个样本后调用 `onChunk(base64)`。
- `stop()` 断开节点并关闭 AudioContext。

- [ ] **Step 4: 实现 PCM 播放器**

`PcmAudioPlayer` 使用单个 24 kHz `AudioContext`，维护 `nextStartTime` 和活动 `AudioBufferSourceNode` 集合：

```ts
enqueue(base64Pcm: string): void;
clear(): void;
close(): Promise<void>;
```

`clear()` 必须停止所有活动 source、清空集合并把 `nextStartTime` 重置为 `audioContext.currentTime`。

- [ ] **Step 5: 验证并提交**

Run:

```bash
cd frontend
npm test
npm run build
```

```bash
git add frontend/public frontend/src/media
git commit -m "feat: 支持实时 PCM 音频"
```

**PR 标题:** `支持实时 PCM 音频采集与播放`

**功能描述:** 麦克风音频按后端要求转换为 16 kHz PCM16，AI 返回的 24 kHz PCM16 音频按序播放并可立即清空。

**实现思路:** AudioWorklet 负责低延迟采样，主线程做轻量重采样和分块，Web Audio 负责有序播放。

**测试方式:** `cd frontend && npm test && npm run build`

---

## PR 6：实现低成本摄像头抽帧

**单一功能:** 从实时预览生成受大小与网络缓冲约束的 JPEG 帧。

**分支:** `codex/video-sampling`

**Files:**

- Create: `frontend/src/media/video-frame-sampler.ts`
- Create: `frontend/src/media/video-frame-sampler.test.ts`

- [ ] **Step 1: 写帧元数据测试**

```ts
it("为每帧生成递增序列和当前时间戳", () => {
  const sampler = new VideoFrameSampler({
    video: document.createElement("video"),
    onFrame: vi.fn(),
    getBufferedAmount: () => 0,
    now: () => 1781234567890,
  });

  expect(sampler.nextMetadata()).toEqual({
    sequence: 1,
    timestamp: 1781234567890,
  });
  expect(sampler.nextMetadata().sequence).toBe(2);
});
```

再覆盖：

```ts
expect(sampler.shouldSkipFrame(300_000, true)).toBe(true);
expect(sampler.shouldSkipFrame(0, false)).toBe(true);
```

- [ ] **Step 2: 实现 VideoFrameSampler**

构造参数：

```ts
interface VideoFrameSamplerOptions {
  video: HTMLVideoElement;
  onFrame: (frame: {
    data: string;
    timestamp: number;
    sequence: number;
  }) => void;
  getBufferedAmount: () => number;
  now?: () => number;
  intervalMs?: number;
}
```

行为：

- 默认每 1000ms 尝试一次。
- `document.visibilityState !== "visible"` 时不抽帧。
- `bufferedAmount > 256 * 1024` 时跳帧。
- 按比例把长边缩到 960px。
- 首次使用 JPEG 质量 0.68；超过 512 KiB 时依次尝试 0.55、0.42。
- 移除 `data:image/jpeg;base64,` 前缀。
- 只在拿到合法 JPEG Base64 后增加 sequence 并调用 `onFrame`。
- `stop()` 清理 timer。

- [ ] **Step 3: 验证并提交**

Run:

```bash
cd frontend
npm test
npm run build
```

```bash
git add frontend/src/media/video-frame-sampler*
git commit -m "feat: 增加低成本视频抽帧"
```

**PR 标题:** `增加低成本摄像头抽帧`

**功能描述:** 以约 1 fps 发送 960px 以内的 JPEG，页面隐藏或 WebSocket 缓冲过高时自动跳帧。

**实现思路:** 复用 Canvas，按质量梯度压缩，不建立视频队列，适配后端 latest-only 调度。

**测试方式:** `cd frontend && npm test && npm run build`

---

## PR 7：接通实时视觉会话

**单一功能:** 设备确认后启动 WebSocket 云会话，并接通音频、视频、文本和中断事件。

**分支:** `codex/live-session`

**Files:**

- Create: `frontend/src/session/session-orchestrator.ts`
- Create: `frontend/src/hooks/useSession.ts`
- Create: `frontend/src/components/LiveSessionScreen.tsx`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/ControlDock.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/App.test.tsx`
- Modify: `frontend/src/styles/components.css`

- [ ] **Step 1: 写开始会话测试**

使用依赖注入的 fake orchestrator，断言：

```tsx
it("确认设备后启动会话并在 connected 前不发送媒体", async () => {
  const start = vi.fn();
  const createOrchestrator = vi.fn(() => ({
    start,
    sendText: vi.fn(),
    setMuted: vi.fn(),
    setVideoPaused: vi.fn(),
    stop: vi.fn(),
    destroy: vi.fn(),
  }));
  render(<App createOrchestrator={createOrchestrator} />);

  fireEvent.click(screen.getByRole("button", { name: "开始视觉对话" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "开始会话" }),
  );

  expect(start).toHaveBeenCalledTimes(1);
  expect(screen.getByText("正在连接")).toBeInTheDocument();
});
```

- [ ] **Step 2: 实现 SessionOrchestrator**

构造依赖：

```ts
interface SessionOrchestratorOptions {
  wsUrl: string;
  protocolStage: number;
  dispatch: React.Dispatch<SessionAction>;
}
```

必须实现：

```ts
start(stream: MediaStream, video: HTMLVideoElement): void;
sendText(text: string): void;
setMuted(muted: boolean): void;
setVideoPaused(paused: boolean): void;
stop(): void;
destroy(): void;
```

事件映射：

- socket open → 发送 `start_session`。
- `status: connected` → 启动 `AudioCapture` 和 `VideoFrameSampler`。
- `audio` → `PcmAudioPlayer.enqueue()`。
- `text` / `user_text` / `turn_complete` → reducer action。
- `interrupted` → `player.clear()` 后 dispatch。
- terminal status → 停止采集但保持 WebSocket，等待 usage。
- `usage` → dispatch 并显示结果。
- `go_away` → phase `recovering`，不新建浏览器 WebSocket。
- `stop()` → 发送 `stop_session`，停止采集。
- `destroy()` → 停止全部控制器并关闭 WebSocket。

- [ ] **Step 3: 实现 useSession**

Hook 返回：

```ts
{
  state,
  startSession,
  sendText,
  toggleMute,
  toggleVideo,
  stopSession,
}
```

orchestrator 保存在 `useRef`，避免 React 重渲染重建媒体对象。

`App` 接受可选依赖，生产环境使用默认实现，测试可注入 fake：

```ts
export interface SessionControls {
  start(stream: MediaStream, video: HTMLVideoElement): void;
  sendText(text: string): void;
  setMuted(muted: boolean): void;
  setVideoPaused(paused: boolean): void;
  stop(): void;
  destroy(): void;
}

export interface AppProps {
  createOrchestrator?: (
    options: SessionOrchestratorOptions,
  ) => SessionControls;
}
```

- [ ] **Step 4: 实现实时页面**

`LiveSessionScreen` 包含：

- 全屏 `<video>`。
- `StatusBadge` 中文状态。
- LIVE、麦克风和摄像头隐私指示。
- 最新问答字幕卡。
- `ControlDock`：静音、暂停画面、翻转镜头、结束。
- 翻转镜头通过重新调用 `MediaController.open({ facingMode })`，成功后替换 stream。

控制按钮必须有 `aria-label` 和 `aria-pressed`。

- [ ] **Step 5: 验证并提交**

Run:

```bash
cd frontend
npm test
npm run build
```

```bash
git add frontend/src
git commit -m "feat: 接通实时视觉会话"
```

**PR 标题:** `接通实时视觉与语音会话`

**功能描述:** 从设备检测进入实时会话，发送音频、视频和文字，播放 AI 音频并支持用户打断与四项会中控制。

**实现思路:** Session Orchestrator 统一管理协议和媒体生命周期，React 只渲染 reducer 状态。

**测试方式:** `cd frontend && npm test && npm run build`

---

## PR 8：增加完整对话记录与文字输入

**单一功能:** 提供最新问答卡、完整记录抽屉和文字提问。

**分支:** `codex/transcript-drawer`

**Files:**

- Create: `frontend/src/components/TranscriptDrawer.tsx`
- Modify: `frontend/src/components/LiveSessionScreen.tsx`
- Modify: `frontend/src/app/session-reducer.ts`
- Modify: `frontend/src/app/session-reducer.test.ts`
- Modify: `frontend/src/styles/components.css`

- [ ] **Step 1: 写转写聚合测试**

覆盖三个行为：

```ts
it("把连续 AI 文本片段追加到当前消息", () => {
  const first = sessionReducer(initialSessionState, {
    type: "MODEL_TEXT",
    text: "杯子在",
  });
  const second = sessionReducer(first, {
    type: "MODEL_TEXT",
    text: "电脑右侧",
  });
  expect(second.messages.at(-1)?.text).toBe("杯子在电脑右侧");
});

it("turn_complete 固化 AI 消息", () => {
  const stateWithStreamingAssistant: SessionState = {
    ...initialSessionState,
    phase: "speaking",
    messages: [{
      id: "assistant-1",
      role: "assistant",
      text: "杯子在电脑右侧",
      source: "voice",
      complete: false,
    }],
  };
  const next = sessionReducer(stateWithStreamingAssistant, {
    type: "TURN_COMPLETE",
  });
  expect(next.messages.at(-1)?.complete).toBe(true);
});

it("协议阶段低于 8 时可以插入语音占位", () => {
  const next = sessionReducer(initialSessionState, {
    type: "VOICE_TURN_STARTED",
  });
  expect(next.messages.at(-1)?.text).toBe("语音提问");
});
```

- [ ] **Step 2: 完善 reducer 消息聚合**

规则：

- `USER_TEXT` 追加到当前 voice user message。
- `VOICE_TURN_STARTED` 只在没有未完成用户消息时创建占位。
- 文字输入直接创建完整 user message。
- `MODEL_TEXT` 聚合连续 assistant 片段。
- `TURN_COMPLETE` 固化当前 assistant 消息。

- [ ] **Step 3: 实现 TranscriptDrawer**

Props：

```ts
interface TranscriptDrawerProps {
  open: boolean;
  messages: TranscriptMessage[];
  protocolStage: number;
  onClose: () => void;
  onSendText: (text: string) => void;
}
```

功能：

- 桌面右下抽屉，移动端底部 70vh。
- 按角色渲染中文标签“你”和“AI”。
- 空记录显示“开始提问后，对话会出现在这里”。
- 输入长度上限 2000，空白不可发送。
- `Escape` 关闭；打开后焦点进入输入框。
- 用户语音转写只在 protocol stage >= 8 时展示精确文本，否则保留“语音提问”。

- [ ] **Step 4: 接入实时页面**

最新问答卡点击打开抽屉；同时提供明确的“查看对话记录”按钮。输入发送成功后清空文本，但不自动关闭抽屉。

- [ ] **Step 5: 验证并提交**

Run:

```bash
cd frontend
npm test
npm run build
```

```bash
git add frontend/src
git commit -m "feat: 增加完整对话记录"
```

**PR 标题:** `增加完整对话记录与文字提问`

**功能描述:** 用户可查看语音与文字问答历史，并在实时会话中继续发送文字问题。

**实现思路:** reducer 聚合流式转写；协议阶段 8 使用真实用户转写，旧部署降级为语音轮次占位。

**测试方式:** `cd frontend && npm test && npm run build`

---

## PR 9：增加异常恢复与会话结果

**单一功能:** 对连接中断和终止状态提供分级反馈，并展示最终 usage。

**分支:** `codex/session-recovery-summary`

**Files:**

- Create: `frontend/src/components/SessionSummary.tsx`
- Modify: `frontend/src/protocol/websocket-client.ts`
- Modify: `frontend/src/session/session-orchestrator.ts`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/App.test.tsx`
- Modify: `frontend/src/styles/components.css`
- Modify: `README.md`

- [ ] **Step 1: 写终止后等待 usage 的 UI 测试**

```tsx
it("终止状态收到 usage 后展示结果", () => {
  const { rerender } = render(
    <SessionSummary
      terminalStatus="budget_exceeded"
      usage={null}
      messages={[]}
      onRestart={vi.fn()}
      onOpenTranscript={vi.fn()}
    />,
  );
  expect(screen.getByText("正在整理本次会话")).toBeInTheDocument();

  rerender(
    <SessionSummary
      terminalStatus="budget_exceeded"
      usage={{
      audio_bytes: 32000,
      text_chars: 20,
      video_frames: 8,
      video_replaced_frames: 2,
      video_bytes: 180000,
      input_tokens: 1200,
      output_tokens: 340,
      total_tokens: 1540,
      duration_ms: 25000,
      first_response_latency_ms: 480,
      }}
      messages={[]}
      onRestart={vi.fn()}
      onOpenTranscript={vi.fn()}
    />,
  );

  expect(screen.getByText("已达到本次会话额度")).toBeInTheDocument();
  expect(screen.getByText("1,540")).toBeInTheDocument();
});
```

- [ ] **Step 2: 实现有限重连**

`WebSocketClient` 增加：

```ts
private reconnectAttempts = 0;
private readonly reconnectDelays = [500, 1000, 2000];
```

仅异常关闭时重连，最多 3 次。每次重连前通知 `recovering`；正常 `close()`、用户停止和 terminal status 不触发浏览器 WebSocket 重连。

- [ ] **Step 3: 实现结果页面**

`SessionSummary` 映射：

```ts
const terminalCopy: Record<TerminalStatus, string> = {
  stopped: "本次会话已结束",
  idle_timeout: "长时间没有收到输入，会话已自动结束",
  max_duration: "已达到单次会话最长时间",
  budget_exceeded: "已达到本次会话额度",
};
```

展示：

- 持续时间，格式 `mm:ss`。
- 首响应延迟，缺失时显示“未产生回答”。
- total/input/output tokens。
- 视频帧和替换帧。
- “查看对话记录”和“再次开始”。

- [ ] **Step 4: 完善分级异常反馈**

- `recovering`：非阻断顶部提示。
- 权限和设备错误：设备检测阻断面板。
- 服务端 `error`：保留会话，根据中文内容显示轻提示。
- 重连 3 次失败：结束面板“连接失败，请检查网络后重新开始”。
- `budget_exceeded` 不自动重启。

- [ ] **Step 5: 更新 README**

在根 `README.md` 增加前端运行说明：

```markdown
## 前端本地运行

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

默认连接 `ws://localhost:8000/ws`。前端不会接触 Gemini API Key。
```

并把“本仓库不包含前端代码”改为“前后端分别位于 `frontend/` 与 `backend/`，只通过公开协议协作”。

- [ ] **Step 6: 最终轻量验证**

Run:

```bash
cd backend
uv run pytest -q
cd ../frontend
npm test
npm run build
```

Expected: 后端测试通过；前端测试和构建通过。

使用浏览器手工验证：

1. `1366×768`：入口、设备检测、实时画面、抽屉、结果页。
2. `390×844`：无横向溢出，控制按钮不小于 44px。
3. 开启系统“减少动态效果”：氛围与状态动画降级。
4. 模拟 `interrupted`：旧 AI 音频立即停止。
5. 模拟 `budget_exceeded` + `usage`：结果页显示中文原因和用量。

- [ ] **Step 7: 提交**

```bash
git add frontend README.md
git commit -m "feat: 增加会话恢复与结果页"
```

**PR 标题:** `增加会话恢复与结果页`

**功能描述:** 短暂断线自动恢复，权限和终止状态提供中文反馈；结束后展示用量、延迟和再次开始入口。

**实现思路:** WebSocket 使用三次有限退避；terminal status 与 usage 分开处理，确保结果数据完整。

**测试方式:** `cd backend && uv run pytest -q`，然后 `cd frontend && npm test && npm run build`，并完成桌面与移动端主流程检查。

---

## 规格覆盖自审

| 规格要求 | 对应 PR |
|---|---|
| 用户语音转写 | PR 1 |
| 独立 Vite React 前端与视觉规范 | PR 2 |
| 摄像头预览、麦克风电平、设备选择 | PR 3 |
| 强类型协议、心跳、未知事件容错 | PR 4 |
| 16 kHz PCM 输入、24 kHz PCM 输出、打断清理 | PR 5 |
| 低帧率 JPEG、缓冲跳帧、后台暂停 | PR 6 |
| 显式 start/stop、实时状态、四项控制 | PR 7 |
| 最新问答、完整记录、文字输入、协议降级 | PR 8 |
| 分级恢复、terminal + usage、结果页、响应式检查 | PR 9 |

## 明确不纳入本轮

- 登录、云端历史、多人会话。
- 屏幕共享、文件上传、工具调用和搜索。
- 前端 Docker、Cloud Build 或 SSR。
- 浏览器 SpeechRecognition。
- 大规模端到端测试矩阵。
- 浏览器端视觉模型或本地语音活动检测。
