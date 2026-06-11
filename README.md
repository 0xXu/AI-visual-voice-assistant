# AI 视觉对话助手

这是一个基于 Gemini Live API 的实时视觉对话服务。客户端通过 WebSocket 持续发送麦克风音频、摄像头画面和文本，后端将数据转发给 Gemini Live，并把模型生成的语音和文字实时返回客户端。

## 已实现功能

### 实时多模态交互

- 接收 16 kHz、16 位、小端 PCM 音频。
- 接收 JPEG 摄像头画面。
- 接收文本对话输入。
- 返回 24 kHz PCM 语音和文字转写。
- 返回 `turn_complete` 事件标记模型本轮回复结束。

### Gemini Live 服务

- 使用 Google AI Studio 的 `GEMINI_API_KEY` 建立会话。
- 默认模型为 `gemini-3.1-flash-live-preview`。
- 使用 Google Gen AI SDK 的异步 Live API。
- 启用自动语音活动检测。
- 启用输入和输出语音转写。
- 会话结束时主动关闭 Gemini 客户端连接。

### 视觉对话规则

系统提示词要求模型：

- 优先回答用户当前问题，避免机械复述整个画面。
- 看不清时明确说明无法确认，不编造视觉信息。
- 区分可见事实与合理推测。
- 主动提醒台阶、车辆、明火等即时危险。
- 准确朗读画面中可辨认的文字。
- 不猜测人物身份或敏感属性。
- 默认使用简短、自然的表达，并跟随用户使用的语言。

### 消息安全校验

客户端消息进入模型服务前会经过以下检查：

- JSON 结构校验
- 消息类型校验
- Base64 严格解码
- 音频和图片大小限制
- 空文本和文本长度限制

无效消息会收到中文错误提示，不会直接中断当前会话。

### WebSocket 会话管理

- `/ws` 提供实时双向通信。
- 并行处理客户端输入、模型响应和连接心跳。
- 支持 `ping`、`pong` 保活消息。
- 任一主要任务结束后取消其余后台任务。
- 客户端断开时释放 Gemini 会话。
- 应用运行日志统一使用中文。

## 技术栈

- Python 3.11
- FastAPI
- Google Gen AI SDK
- Pydantic Settings
- uv
- pytest

## 本地运行

### 1. 安装 uv

参考 [uv 官方文档](https://docs.astral.sh/uv/) 安装 uv。

### 2. 安装依赖

```bash
cd backend
uv sync --locked
```

### 3. 配置 API Key

创建本地环境文件：

```bash
cp .env.example .env
```

编辑 `backend/.env`：

```env
GEMINI_API_KEY=你的_Google_AI_Studio_API_Key
```

可选配置：

```env
MODEL_NAME=gemini-3.1-flash-live-preview
VOICE_NAME=Aoede
CORS_ORIGINS=http://localhost:3000
WEBSOCKET_KEEPALIVE_SECONDS=20
MAX_AUDIO_BYTES=262144
MAX_VIDEO_BYTES=2097152
MAX_TEXT_CHARS=2000
```

### 4. 启动服务

在 `backend` 目录执行：

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

服务地址：

- 健康检查：`http://localhost:8000/health`
- WebSocket：`ws://localhost:8000/ws`
- API 文档：`http://localhost:8000/docs`

检查服务状态：

```bash
curl http://localhost:8000/health
```

响应示例：

```json
{
  "status": "ok"
}
```

## WebSocket 消息协议

### 文本输入

```json
{
  "type": "text",
  "data": "请描述摄像头中的画面"
}
```

### 音频输入

```json
{
  "type": "audio",
  "data": "<Base64 PCM 音频>"
}
```

音频格式：

- 单声道
- 16 位 PCM
- 小端字节序
- 16 kHz 采样率

### 视频帧输入

```json
{
  "type": "video_frame",
  "data": "<Base64 JPEG 图片>"
}
```

### 心跳消息

```json
{
  "type": "ping",
  "data": ""
}
```

### 模型音频响应

```json
{
  "type": "audio",
  "data": "<Base64 PCM 音频>"
}
```

模型音频为单声道、16 位、24 kHz PCM。

### 文字转写

```json
{
  "type": "text",
  "data": "模型语音回复的文字转写"
}
```

### 本轮回复完成

```json
{
  "type": "turn_complete",
  "data": ""
}
```

### 错误响应

```json
{
  "type": "error",
  "data": "中文错误信息"
}
```

## 测试

```bash
cd backend
uv sync --locked
uv run pytest -v
uv run python -m compileall -q app tests
```

测试覆盖：

- 健康检查接口
- API Key 配置校验
- CORS 来源解析
- JSON 和消息类型校验
- Base64 与媒体大小校验
- 文本内容校验
- AI Studio 客户端创建
- Gemini Live 音频、视频和文本输入
- 中文视觉助手提示词规则
- WebSocket 多模态消息转发
- 无效消息的中文错误处理

## 项目结构

```text
backend/
├── app/
│   ├── api/
│   │   ├── messages.py
│   │   └── websocket.py
│   ├── core/
│   │   └── config.py
│   ├── services/
│   │   └── gemini_service.py
│   └── main.py
├── tests/
├── .env.example
├── .python-version
├── pyproject.toml
└── uv.lock
```
