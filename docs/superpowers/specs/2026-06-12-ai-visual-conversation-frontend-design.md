# AI 视觉对话助手前端设计规格

**日期**: 2026-06-12

**状态**: 已完成交互设计确认，等待用户审核书面规格

**定位**: 比赛演示优先，产品故事为通用视觉问答

**前端仓库形态**: 与现有 Python 后端完全分离的独立静态 SPA

## 1. 目标

开发一个桌面浏览器优先、移动端完整可用的实时视觉对话前端。用户允许摄像头和麦克风后，可以自然地向 AI 提问；AI 能结合画面与声音进行语音回答，并提供可展开的完整对话记录。

设计优先级依次为：

1. 比赛现场能够稳定、快速地进入演示。
2. 用户能明确感知 AI 正在聆听、思考或回答。
3. 用户能随时打断 AI、暂停媒体或结束会话。
4. 视频带宽与 Gemini 会话成本受到前后端共同约束。
5. 前后端通过公开 WebSocket 协议协作，不共享代码模块。

## 2. 用户故事

### 首版必须实现

- 作为首次用户，我能先查看摄像头预览、麦克风电平并选择输入设备，再开始云端会话。
- 作为用户，我能看到 AI 当前处于连接、聆听、思考、回答或恢复状态。
- 作为用户，我能用语音和文字提出与当前画面相关的问题。
- 作为用户，我能听到低延迟的 AI 语音回答，并看到同步文本。
- 作为用户，我说话时能立即打断正在播放的 AI 回答。
- 作为用户，我能静音、暂停摄像头、翻转镜头和结束会话。
- 作为用户，我能展开完整记录，并在其中继续输入文字问题。
- 作为用户，我能理解权限拒绝、断线、超时、最大时长和预算终止的原因。
- 作为用户，我在会话结束后能看到时长、首响应延迟、token 和媒体用量摘要。

### 首版不实现

- 登录、账户、云端历史记录和跨设备同步。
- 多房间、多用户或多人会议。
- 浏览器端模型推理和离线视觉理解。
- 工具调用、网页搜索、文件上传和屏幕共享。
- 自定义角色市场、复杂设置中心或运营后台。

## 3. 技术方案

采用 **Vite + React + TypeScript** 构建静态 SPA。

选择理由：

- 当前后端只有 WebSocket 实时协议，没有 SSR、SEO 或服务端路由需求。
- React 适合按设备检测、实时舞台、记录抽屉和结果面板拆分视觉状态。
- TypeScript 判别联合可约束客户端与服务端消息处理。
- Vite 产物可独立静态部署，不需要恢复已删除的 Docker 前端配置。
- 不引入 Redux、Zustand、GSAP 或大型组件库，降低比赛开发和调试成本。

### 核心依赖

- React、React DOM、TypeScript、Vite。
- Lucide React：统一图标。
- 浏览器原生 WebSocket、MediaDevices、Web Audio、AudioWorklet、Canvas。
- CSS Modules 或按功能拆分的原生 CSS。首版不引入 Tailwind。

## 4. 页面与组件

### 4.1 入口屏

- 深海科技背景和简短产品定位。
- 一个主要操作：“开始视觉对话”。
- 简短说明摄像头和麦克风用途。
- 不在用户明确操作前请求设备权限或连接 Gemini。

### 4.2 设备检测屏

- 摄像头预览。
- 麦克风实时电平。
- 摄像头和麦克风选择器。
- 权限拒绝、无设备和设备占用的中文恢复指引。
- “开始会话”仅在视频和音频均可用时启用。

设备枚举在获得权限后进行，因为未授权时浏览器可能隐藏设备标签。

### 4.3 实时会话屏

- 摄像头视频全屏显示。
- 左上显示状态：正在连接、正在聆听、正在思考、正在回答、正在恢复。
- 右上显示 LIVE、摄像头和麦克风隐私状态。
- 底部显示最新问答卡；点击或上滑打开完整记录。
- 控制栏包含：静音、暂停摄像头、翻转镜头、结束。
- 记录抽屉包含全部消息、当前流式文本和文字输入框。

### 4.4 结果屏

- 显示正常结束或具体终止原因。
- 显示 `duration_ms`、`first_response_latency_ms`、token、视频帧和替换帧。
- 保留本地记录供用户查看。
- 提供“再次开始”，复用当前浏览器 WebSocket 或重新建立连接。

## 5. 模块边界

```text
React UI
  ├── EntryScreen
  ├── DeviceCheckScreen
  ├── LiveSessionScreen
  ├── TranscriptDrawer
  └── SessionSummary
          │ intents / state
Session Coordinator
  ├── sessionReducer
  ├── SessionOrchestrator
  └── protocol types + parser
          │ commands / events
Browser Capability Layer
  ├── WebSocketClient
  ├── MediaController
  ├── AudioCaptureWorklet
  ├── VideoFrameSampler
  └── PcmAudioPlayer
```

### UI 层

只渲染状态并发送用户意图。不得直接操作 WebSocket、AudioContext 或 MediaStreamTrack。

### 会话协调层

统一控制启动、暂停、恢复和清理。使用 `useReducer` 管理复杂但有限的状态转换，不使用全局状态库。

### 浏览器能力层

持有非 React 资源。所有控制器都提供幂等 `start()` / `stop()`，并在组件卸载、结束会话和异常退出时统一清理。

## 6. 状态机

```text
idle
  -> device_check
  -> connecting
  -> listening <-> thinking <-> speaking
  -> recovering -> listening
  -> ended
```

关键规则：

- 用户点击开始后才发送 `start_session`。
- 收到 `status: connected` 后才发送音频、视频或文字。
- 收到首个模型文本或音频后进入 `speaking`。
- `turn_complete` 结束当前 AI 消息并回到 `listening`。
- `interrupted` 立即清空播放队列并回到 `listening`。
- `go_away` 显示轻量恢复提示；后端负责 Gemini 连接恢复，浏览器 WebSocket 保持打开。
- terminal status 先停止媒体，等待唯一 `usage` 后进入完整结果态。
- 未知消息和未知状态记录中文警告，但不使应用崩溃。

## 7. 协议与数据流

### 输入音频

- 使用 AudioWorklet 在音频线程处理输入。
- 重采样为 PCM signed 16-bit little-endian、mono、16 kHz。
- 每 20–40ms 形成一个音频块，严格小于后端 8192 字节限制。
- 静音时设置音频轨道 `enabled = false` 并停止发送有效音频块。

### 输入视频

- 从 `<video>` 绘制到复用的 Canvas 并输出 JPEG。
- 默认长边 960px、质量约 0.68，单帧必须小于 524288 字节。
- 默认约 1 fps；画面稳定、标签页隐藏或网络拥塞时降到 0.5 fps 或暂停。
- 每帧带递增 `sequence` 和发送时的 Unix epoch 毫秒 `timestamp`。
- 前端只保留当前待发帧，不建立视频发送队列。

### 输出音频

- 解码 Base64 PCM16 mono 24 kHz。
- 使用有序播放队列避免音频块重叠或乱序。
- `interrupted`、用户结束或 terminal status 立即停止当前节点并清空队列。

### 转写

- 服务端 `text` 作为 AI 转写追加到当前 AI 消息。
- `turn_complete` 固化当前 AI 消息。
- 完整用户语音气泡依赖后端新增 `user_text` 事件，数据为 Gemini input transcription。
- 该能力未部署时，前端显示“语音提问”占位，仍可正常完成主流程。
- 不使用浏览器 SpeechRecognition 作为主方案。

### 心跳

- 收到服务端 `ping` 立即回复 `pong`。
- 可在空闲时发送客户端 `ping`，以 `pong` 判断浏览器 WebSocket 是否仍可用。

## 8. 后端协议补充

当前主分支协议阶段 7 已启用 Gemini `input_audio_transcription`，但 `GeminiSession.receive()` 仅转发输出转写。

前端完整问答记录需要一个独立后端 PR：

```json
{"type":"user_text","data":"用户语音转写文本"}
```

要求：

- 从 Gemini `server_content.input_transcription.text` 读取文本。
- 仅转发非空文本。
- 更新 `docs/frontend-integration-contract.md` 并提高 protocol stage。
- 前端根据部署元数据中的 protocol stage 启用用户文本气泡。
- 不从 GitHub 合并状态推断线上能力。

Google Gemini Live 官方能力说明确认输入和输出音频均可提供转写。

## 9. 成本控制

### 已采用

- 用户显式开始后才创建 Gemini 会话。
- 低分辨率 JPEG、低帧率和 latest-only 视频。
- `WebSocket.bufferedAmount` 超过阈值时跳过视频帧，不继续堆积。
- 标签页隐藏时暂停视频抽帧。
- 用户暂停摄像头时停止视频上传。
- 后端继续负责空闲超时、最大时长、token 预算和 usage 汇总。
- 结果屏向演示者显示 token、帧数和首响应延迟。

### 暂不采用

- 浏览器端视觉变化检测模型：增加包体和 CPU 成本，首版收益不足。
- 本地语音活动检测替代云端活动检测：可能破坏自然打断。
- 动态模型路由：当前后端只有一个 Gemini Live 会话模型。
- 客户端持有 Gemini Key 直连：不符合安全边界。

## 10. 异常与恢复

| 情况 | UI | 行为 |
|---|---|---|
| 短暂 WebSocket 断开 | 非阻断提示 | 停止发送并有限次数重连，保留本地记录 |
| `go_away` | “正在恢复实时连接” | 等待后端透明恢复 |
| 权限拒绝 / 无设备 | 阻断面板 | 返回设备检测并展示中文恢复步骤 |
| `idle_timeout` | 结束面板 | 停止媒体，等待 usage，可重新开始 |
| `max_duration` | 结束面板 | 解释达到单次会话时长限制 |
| `budget_exceeded` | 成本保护面板 | 展示 token，不自动重启 |
| `interrupted` | 无弹窗 | 立即停止 AI 音频并回到聆听 |
| 未知协议消息 | 轻量警告或忽略 | 不崩溃，不执行危险默认行为 |

WebSocket 重连采用有限退避，不无限重试。预算耗尽、最大时长和用户结束都是终止状态。

## 11. 视觉与响应式

视觉细节以根目录 `DESIGN.md` 为唯一实现规范。

- 桌面端优先保证 1366×768 演示效果。
- 移动端小于 640px 时，记录变为 70vh 底部抽屉。
- 横屏低高度环境将控制栏移到右侧，避免遮挡字幕。
- 所有触控目标至少 44×44px。
- 支持 `prefers-reduced-motion`。
- 镜头上使用暗色方向渐变保证文字对比度。

## 12. 测试策略

测试以快速交付和核心风险为边界。

### 单元测试

- reducer 的关键状态转换。
- 服务端消息解析和未知事件容错。
- PCM16 编解码、音频队列清空。
- JPEG 大小、timestamp 和 sequence 生成。
- terminal status 后等待 usage 的顺序。

### 浏览器主流程

只建立一条稳定的真实浏览器流程：

1. 授权摄像头和麦克风。
2. 完成设备检测。
3. 发送 `start_session` 并等待 `connected`。
4. 模拟文本、音频、用户打断和 `turn_complete`。
5. 发送 `stop_session`。
6. 验证 terminal status 和 usage 结果面板。

### 手工检查

- Chrome 桌面 1366×768。
- Chrome 移动端 390×844。
- 权限拒绝、无摄像头、静音、暂停画面和断线恢复。
- 明亮与暗色摄像头画面下的字幕可读性。

首版不建立多浏览器、多设备和长时间压力测试矩阵。

## 13. 验收标准

- 页面加载后不会自动请求权限或创建云端会话。
- 设备检测能展示预览、麦克风电平和设备选择。
- `connected` 前不发送媒体。
- 视频和音频严格符合现有后端协议限制。
- 用户能自然打断 AI，旧音频不继续播放。
- 四项会中控制全部可用并有明确状态。
- 完整记录支持 AI 文本、文字问题和可选用户语音转写。
- 所有 terminal status 都有中文解释并展示最终 usage。
- 桌面与移动端无横向溢出，交互目标不小于 44px。
- API Key 不进入浏览器代码、构建产物或存储。

## 14. 参考资料

- [Gemini Live API](https://ai.google.dev/gemini-api/docs/live-api)
- [Gemini Live API capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities)
- [AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)
- [WebSocket bufferedAmount](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/bufferedAmount)
- [Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)
- [React useReducer](https://react.dev/reference/react/useReducer)
- [Vite static deployment](https://vite.dev/guide/static-deploy)
