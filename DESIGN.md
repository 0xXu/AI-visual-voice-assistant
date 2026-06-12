# AI 视觉对话助手前端设计规范

> 让摄像头画面成为界面主体，用安静、清晰、可恢复的交互承载实时视觉对话。

## 1. Visual Theme & Atmosphere

**Style**: 深海科技（Deep Sea Technology）

**Keywords**: 沉浸、冷静、实时、可信、低噪声、通透、克制

**Tone**: 近黑海军蓝与冰青状态光，强调镜头内容和 AI 反馈，而不是装饰性科技元素。

**Not**: 高饱和赛博朋克、密集扫描线、故障文字、过度发光、仪表盘式信息堆叠。

**Feel**: 像在安静的深海观察窗前，与一个始终专注于当前画面的助手交谈。

**Interaction Tier**: L2 流畅交互

**Dependencies**: React + CSS Animation + Web Animations API；不使用 GSAP、Lenis 或常驻 WebGL。

入口使用低成本 Soft Aurora 氛围层。实时会话中，摄像头视频占满视口，所有 UI 都是可读但克制的悬浮层。

## 2. Color Palette & Roles

```css
:root {
  color-scheme: dark;

  /* Backgrounds */
  --color-bg: #030913;
  --color-bg-elevated: #071522;
  --color-surface: #0d2234;
  --color-surface-alt: #102a40;
  --color-surface-hover: #15344b;
  --color-overlay: rgba(3, 12, 20, 0.76);

  /* Borders */
  --color-border: rgba(135, 220, 255, 0.20);
  --color-border-hover: rgba(135, 220, 255, 0.42);

  /* Text */
  --color-text: #effbff;
  --color-text-secondary: #b8d0dc;
  --color-text-tertiary: #91adbd;

  /* Accent */
  --color-accent: #70ddff;
  --color-accent-hover: #94e7ff;
  --color-accent-secondary: #7598ff;

  /* Semantic */
  --color-success: #65e6bf;
  --color-warning: #ffd071;
  --color-error: #ff7186;

  /* RGB variants */
  --color-bg-rgb: 3, 9, 19;
  --color-surface-rgb: 13, 34, 52;
  --color-accent-rgb: 112, 221, 255;
  --color-success-rgb: 101, 230, 191;
  --color-warning-rgb: 255, 208, 113;
  --color-error-rgb: 255, 113, 134;
}
```

**Color Rules**

- 所有颜色必须通过 CSS 变量引用，不在组件中写新的十六进制颜色。
- 冰青表示连接、聆听和主要操作；琥珀表示思考和等待；薄荷绿表示成功；红色只表示结束或错误。
- 视频上方必须叠加方向性暗色渐变，确保字幕和控制栏在明亮画面上仍可读。
- 同一状态组件只使用一个语义强调色。
- 正文和实时字幕满足 WCAG AA 对比度；键盘焦点环保持至少 3:1 的状态对比。

## 3. Typography Rules

```css
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap");

:root {
  --font-sans: "Noto Sans SC", "Inter", system-ui, -apple-system,
    BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}
```

| Role | Size | Weight | Line Height | Letter Spacing |
|---|---:|---:|---:|---:|
| Entry H1 | `clamp(42px, 7vw, 88px)` | 700 | 1.05 | -0.04em |
| Screen H2 | `clamp(26px, 4vw, 40px)` | 650 | 1.2 | -0.02em |
| Card H3 | 18px | 600 | 1.45 | 0 |
| AI Caption | `clamp(17px, 2vw, 24px)` | 500 | 1.7 | 0.01em |
| Body | 16px | 400 | 1.75 | 0.02em |
| Label | 12px | 600 | 1.4 | 0.12em |
| Metric | 24px | 600 | 1.2 | -0.02em |

**Typography Rules**

- 中文字体必须排在字体栈首位，正文不得小于 15px。
- 实时字幕使用纯白或次级白，不使用渐变、投影或逐字打字机效果。
- 入口 H1 可仅对一个关键词使用冰青到蓝紫渐变，不叠加文字投影。
- 状态标签使用短句和可识别图标，不使用全大写英文替代中文说明。
- **Never use**: Comic Sans、Papyrus、故障字体、装饰性像素字体。

## 4. Component Stylings

### Primary Button

```css
.button-primary {
  min-height: 48px;
  padding: 0 22px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: var(--color-accent);
  color: var(--color-bg);
  font: 600 15px/1 var(--font-sans);
  cursor: pointer;
  transition: transform 160ms ease, background 160ms ease,
    box-shadow 160ms ease;
}

.button-primary:hover {
  transform: translateY(-1px);
  background: var(--color-accent-hover);
  box-shadow: 0 8px 28px rgba(var(--color-accent-rgb), 0.22);
}

.button-primary:active {
  transform: scale(0.96);
  box-shadow: none;
}

.button-primary:focus-visible {
  outline: 2px solid var(--color-text);
  outline-offset: 3px;
}

.button-primary:disabled {
  cursor: not-allowed;
  opacity: 0.46;
  transform: none;
  box-shadow: none;
}
```

### Icon Control

```css
.icon-control {
  display: inline-grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  background: rgba(var(--color-surface-rgb), 0.86);
  color: var(--color-text);
  cursor: pointer;
  transition: transform 150ms ease, background 150ms ease,
    border-color 150ms ease;
}

.icon-control:hover {
  background: var(--color-surface-hover);
  border-color: var(--color-border-hover);
}

.icon-control:active {
  transform: scale(0.94);
}

.icon-control:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 3px;
}

.icon-control[aria-pressed="true"] {
  color: var(--color-warning);
  border-color: rgba(var(--color-warning-rgb), 0.55);
}

.icon-control--end {
  background: var(--color-error);
  color: var(--color-text);
  border-color: transparent;
}

.icon-control:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}
```

### Glass Panel and Caption

```css
.glass-panel {
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--color-overlay);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 18px 54px rgba(var(--color-bg-rgb), 0.36);
}

.caption-card {
  width: min(720px, calc(100vw - 32px));
  padding: 16px 18px;
  transition: opacity 180ms ease, transform 180ms ease;
}

.caption-card[data-entering="true"] {
  opacity: 0;
  transform: translateY(8px);
}
```

### Status Badge

```css
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-overlay);
  color: var(--color-accent);
  font: 600 12px/1 var(--font-sans);
}

.status-badge[data-state="thinking"] {
  color: var(--color-warning);
}

.status-badge[data-state="speaking"] {
  color: var(--color-success);
}

.status-badge[data-state="error"] {
  color: var(--color-error);
}
```

### Device Card

```css
.device-card {
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--color-surface);
  transition: border-color 180ms ease, transform 180ms ease;
}

.device-card:hover {
  border-color: var(--color-border-hover);
}

.device-card:focus-within {
  outline: 2px solid var(--color-accent);
  outline-offset: 3px;
}

.device-card[data-ready="true"] {
  border-color: rgba(var(--color-success-rgb), 0.45);
}
```

### Transcript Drawer

```css
.transcript-drawer {
  position: fixed;
  z-index: 40;
  right: 16px;
  bottom: 16px;
  width: min(560px, calc(100vw - 32px));
  max-height: min(72vh, 760px);
  overflow: hidden;
  transform: translateY(calc(100% + 24px));
  transition: transform 240ms cubic-bezier(0.16, 1, 0.3, 1);
}

.transcript-drawer[data-open="true"] {
  transform: translateY(0);
}

.transcript-list {
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
```

## 5. Layout Principles

**Screen Model**

1. 入口：居中品牌叙事、主要 CTA、隐私说明。
2. 设备检测：桌面双栏（预览 / 设备控制），移动端单栏。
3. 实时会话：全屏摄像头背景，状态位于左上，隐私与 LIVE 指示位于右上，字幕和控制栏位于底部安全区。
4. 会话结果：居中结果面板，展示结束原因、时长、首响应延迟、token 与视频帧数据。

**Spacing Scale**

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --space-8: 72px;
}
```

**Container**

- 常规内容最大宽度：1200px。
- 设备检测内容最大宽度：1040px。
- 结果面板最大宽度：680px。
- 桌面左右安全边距：24px；移动端：14px。
- 实时字幕底部位置必须避开控制栏和 `env(safe-area-inset-bottom)`。

**Layer Order**

```css
.camera-layer { z-index: 0; }
.camera-scrim { z-index: 1; }
.session-chrome { z-index: 10; }
.caption-layer { z-index: 20; }
.control-dock { z-index: 30; }
.transcript-drawer { z-index: 40; }
.blocking-dialog { z-index: 50; }
```

## 6. Depth & Elevation

| Level | Treatment | Use |
|---|---|---|
| Camera | 无阴影、全屏 `object-fit: cover` | 实时视频 |
| Flat | 1px 低对比边框 | 状态标签、列表项 |
| Subtle | `0 8px 28px rgba(3,9,19,.24)` | 设备卡、输入框 |
| Elevated | `0 18px 54px rgba(3,9,19,.36)` | 字幕卡、控制栏 |
| Blocking | `0 28px 90px rgba(3,9,19,.52)` | 权限错误、结束面板 |

大面积区域不得使用强 `backdrop-filter`。模糊只用于字幕、控制栏和短时面板，最大 12px。

## 7. Animation & Interaction

**Motion Philosophy**: 动效只表达状态变化和空间关系，不制造额外注意力竞争。

**Tier**: L2。

### Entrance and Screen Transition

```css
@keyframes screen-enter {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.screen-enter {
  animation: screen-enter 420ms cubic-bezier(0.16, 1, 0.3, 1) both;
}
```

### Atmosphere Background

```css
@keyframes atmosphere-drift {
  0%, 100% { transform: translate3d(-2%, -1%, 0) scale(1); opacity: 0.44; }
  50% { transform: translate3d(3%, 2%, 0) scale(1.06); opacity: 0.58; }
}

.atmosphere {
  animation: atmosphere-drift 14s ease-in-out infinite;
  will-change: transform, opacity;
}
```

### Session State

```css
@keyframes listening-pulse {
  0%, 100% { transform: scale(0.88); opacity: 0.55; }
  50% { transform: scale(1.08); opacity: 1; }
}

.state-indicator[data-state="listening"]::before {
  animation: listening-pulse 1.8s ease-in-out infinite;
}

.state-indicator[data-state="thinking"]::before {
  animation: listening-pulse 0.9s ease-in-out infinite;
  color: var(--color-warning);
}
```

### Required L2 Signature Moments

- Hero H1：按行淡入并轻微上浮，不逐字拆分中文。
- Section H2：设备检测和结果标题使用一次性 `fadeInUp`。
- Body / Label：隐私说明和状态标签使用短距离淡入。
- Element：主要 CTA 与控制按钮具备按压缩放反馈。
- Interactive Component：对话记录抽屉平滑进出并支持拖拽关闭。
- Background：入口 Soft Aurora；会话中改为真实摄像头，不叠加动态背景。

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }

  .atmosphere {
    transform: none;
    opacity: 0.5;
  }
}
```

## 8. Do's and Don'ts

### Do

- 保持摄像头画面是实时会话中的最大视觉元素。
- 始终显示摄像头和麦克风当前是否启用。
- 使用中文解释权限、断线、超时和预算终止原因。
- 将最新问答保持在拇指和视线容易触达的位置。
- 让所有清理操作幂等，结束后关闭媒体轨道和音频上下文。
- 对未知协议消息做防御性处理，不让界面崩溃。
- 为键盘用户提供可见焦点，为图标按钮提供中文 `aria-label`。
- 用户打断 AI 时立即清空播放队列并回到聆听状态。

### Don't

- 不使用高频扫描线、闪烁故障字或持续粒子雨。
- 不把技术指标常驻在实时画面中央。
- 不使用浏览器 SpeechRecognition 作为核心用户转写来源。
- 不在 WebSocket 尚未收到 `connected` 时发送媒体。
- 不在网络缓冲增长时继续堆积视频帧。
- 不让字幕使用逐字打字机效果。
- 不隐藏浏览器正在使用摄像头和麦克风的事实。
- 不在移动端缩小控制按钮到 44px 以下。
- 不自动重启预算耗尽或最大时长结束的会话。
- 不把 Gemini API Key 写入前端代码、构建变量或浏览器存储。

## 9. Responsive Behavior

| Name | Width | Key Changes |
|---|---:|---|
| Desktop | `>= 1024px` | 设备检测双栏；记录抽屉右下悬浮；字幕最大 720px |
| Tablet | `640px–1023px` | 设备检测单栏；结果面板宽度自适应；控制栏保持单行 |
| Mobile | `< 640px` | 记录抽屉变为 70vh 底部抽屉；字幕全宽；关闭重氛围动画 |

```css
@media (max-width: 639px) {
  .transcript-drawer {
    inset: auto 0 0;
    width: 100%;
    max-height: 70vh;
    border-radius: 22px 22px 0 0;
    padding-bottom: env(safe-area-inset-bottom);
  }

  .caption-card {
    width: calc(100vw - 28px);
    padding: 14px;
  }

  .control-dock {
    bottom: calc(12px + env(safe-area-inset-bottom));
  }

  .atmosphere {
    animation: none;
  }
}

@media (orientation: landscape) and (max-height: 520px) {
  .caption-card {
    max-height: 34vh;
    overflow-y: auto;
  }

  .control-dock {
    right: 12px;
    left: auto;
    flex-direction: column;
  }
}
```

所有交互目标最小为 44×44px。页面不得产生横向滚动；视频使用 `object-fit: cover`，设备检测预览可使用 `contain` 以便检查完整取景范围。
