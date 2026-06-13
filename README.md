# AI 视觉语音助手

这是一个基于 Gemini Live API 的实时多模态视觉语音助手。客户端通过
WebSocket 发送 PCM16 音频、JPEG 画面和文本，后端负责输入校验与调度、
Gemini Live 会话管理、模型音频与转写转发，以及会话用量和生命周期控制。

前后端分别位于 `frontend/` 与 `backend/`，双方只通过
[前端集成协议](docs/frontend-integration-contract.md) 协作。

## 环境要求

- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Google AI Studio `GEMINI_API_KEY`

## 本地运行

```bash
cd backend
uv sync --locked
cp .env.example .env
```

编辑 `backend/.env`，填写真实密钥：

```env
GEMINI_API_KEY=你的_Google_AI_Studio_API_Key
```

启动服务：

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

服务地址：

- 健康检查：`http://localhost:8000/health`
- WebSocket：`ws://localhost:8000/ws`
- OpenAPI：`http://localhost:8000/docs`

## 环境配置

`backend/.env.example` 包含当前全部运行设置和默认值：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `GEMINI_API_KEY` | 空 | 必填的 Google AI Studio 密钥 |
| `MODEL_NAME` | `gemini-3.1-flash-live-preview` | Gemini Live 模型 |
| `VOICE_NAME` | `Aoede` | 模型语音 |
| `CORS_ORIGINS` | `http://localhost:3000` | 逗号分隔的允许来源 |
| `WEBSOCKET_KEEPALIVE_SECONDS` | `20` | 服务端心跳间隔 |
| `MAX_AUDIO_BYTES` | `8192` | 单条音频解码后最大字节数 |
| `MAX_VIDEO_BYTES` | `524288` | 单帧图片解码后最大字节数 |
| `MAX_FRAME_AGE_MS` | `2000` | 图片时间戳允许的前后偏差 |
| `MAX_TEXT_CHARS` | `2000` | 单条文本最大字符数 |
| `AUDIO_QUEUE_CAPACITY` | `32` | 音频队列容量 |
| `TEXT_QUEUE_CAPACITY` | `8` | 文本队列容量 |
| `SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS` | `1.0` | 调度器关闭硬超时 |
| `SESSION_IDLE_SECONDS` | `45.0` | 无已接受输入时的空闲超时 |
| `SESSION_MAX_SECONDS` | `600.0` | 单个逻辑会话最长时间 |
| `SESSION_TOKEN_BUDGET` | `50000` | 单个逻辑会话 token 预算 |

队列容量、媒体限制、超时和 token 预算都必须为正数。token 用量以
Gemini Live 返回的 usage metadata 为准，预算是会话保护限制，不是账单保证。

## 前端本地运行

前端位于 `frontend/`，后端位于 `backend/`，双方只通过
`docs/frontend-integration-contract.md` 中的公开 WebSocket 协议协作。
前端不会接触或打包 Gemini API Key。

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

默认连接 `ws://localhost:8000/ws`。如需修改地址，编辑
`frontend/.env` 中的 `VITE_WS_URL`。

## WebSocket 会话流程

浏览器 WebSocket 与 Gemini 云会话相互独立。同一 WebSocket 可以依次运行
多个云会话：

1. 连接 `ws://localhost:8000/ws`。
2. 发送 `{"type":"start_session"}`。
3. 收到 `{"type":"status","data":"connected"}` 后发送输入。
4. 发送 `{"type":"stop_session"}`，或等待会话因限制结束。
5. 后端先发送终止 `status`，再发送一次 `usage`。
6. WebSocket 保持打开，可以再次发送 `start_session`。

Gemini 会话不会在 `start_session` 前创建。等待启动时仅接受
`start_session`、`ping` 和 `pong`；其他消息会收到
`请先发送 start_session`。活动会话中的重复 `start_session` 是空操作。

终止状态：

| `status.data` | 含义 |
|---|---|
| `stopped` | 主动停止或 Gemini 响应流自然结束 |
| `idle_timeout` | 默认 45 秒没有通过校验并被调度器接受的输入 |
| `max_duration` | 默认达到 600 秒会话上限 |
| `budget_exceeded` | Gemini 累计报告的 token 达到默认 50,000 |

上述终止条件只结束当前云会话。用户主动停止、空闲超时、最长时限和预算
耗尽不会触发自动恢复。

## 输入格式与限制

### 文本

```json
{"type":"text","data":"请描述镜头中的内容"}
```

文本必须非空，默认最多 2,000 个字符。

### 音频

```json
{"type":"audio","data":"<base64-pcm16>"}
```

音频必须是 16 kHz、单声道、16 位小端 PCM。Base64 使用严格校验，解码后
默认不超过 8,192 字节，且 PCM16 字节数必须为偶数。

### 图片

```json
{
  "type":"video_frame",
  "data":"<base64-jpeg>",
  "timestamp":1781234567890,
  "sequence":42
}
```

图片必须通过严格 Base64 校验，解码后默认不超过 524,288 字节，并包含
JPEG SOI/EOI 起止标记。`timestamp` 是 Unix 毫秒整数，默认只接受与后端
时间相差不超过 2,000 ms 的帧；`sequence` 必须递增。

### 心跳

```json
{"type":"ping"}
{"type":"pong"}
```

后端每 20 秒默认发送一次 `ping`，收到客户端 `ping` 时回复 `pong`。

## 输入调度

- 音频和文本分别使用容量为 32 和 8 的有界队列。
- 调度器按批次优先处理文本和音频，同时保证待处理图片能够继续发送。
- 图片只保留最新帧；新序列替换尚未发送的旧帧，重复或倒退序列被忽略。
- 每种音频和文本最多保留一个等待入队的提交；继续拥塞时返回中文错误。
- 只有通过校验且被调度器接受的输入才刷新空闲计时并计入 usage。
- 会话关闭时唤醒等待提交者，在默认 1 秒硬超时内排空或取消后台任务。

## Gemini Live 配置

- 仅使用 Google AI Studio API Key 认证。
- 响应模态为音频，启用输入和输出语音转写。
- 启用自动语音活动检测。
- 媒体分辨率固定为 `LOW`，降低实时视觉输入成本。
- 启用滑动窗口 context compression，控制长会话上下文增长。
- 模型输出音频为 24 kHz、单声道、16 位 PCM。

## 服务端事件

常规模型事件：

```json
{"type":"text","data":"模型转写文本"}
{"type":"audio","data":"<base64-pcm16-24khz>"}
{"type":"turn_complete","data":""}
```

Gemini 报告用户打断时，后端先转发：

```json
{"type":"interrupted","data":""}
```

每个云会话结束时发送一次结构化用量：

```json
{
  "type":"usage",
  "data":{
    "audio_bytes":32000,
    "text_chars":120,
    "video_frames":8,
    "video_replaced_frames":3,
    "video_bytes":180000,
    "input_tokens":1200,
    "output_tokens":340,
    "total_tokens":1540,
    "duration_ms":25000,
    "first_response_latency_ms":480
  }
}
```

`first_response_latency_ms` 在没有完整输入和响应时间点时为 `null`。

Gemini 发布可恢复状态时，后端只公开布尔值，不公开不透明恢复句柄：

```json
{"type":"session_resumption","data":{"resumable":true}}
```

Gemini 要求迁移连接时，后端转发剩余时间：

```json
{"type":"go_away","data":{"time_left_ms":5000}}
```

收到 GoAway 后，后端最多使用最新有效句柄自动恢复一次；恢复连接建立失败时，
最多再回退到一次不带句柄的新连接。恢复前后的空闲时间、最长时限和 usage
计数属于同一个逻辑会话，最终仍只发送一次终止 `status` 和一次 `usage`。

完整消息字段、顺序和兼容性要求见
[前端集成协议](docs/frontend-integration-contract.md)。

## 验证

```bash
cd backend
uv sync --locked
uv run pytest -q
uv run python -m compileall -q app tests
```
