# EchoSight Entry Motion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 EchoSight 入口首屏升级为强烈舞台感动效，同时保持轻量、可访问和业务行为不变。

**Architecture:** `EntryScreen` 只负责指针位置到 CSS 变量的轻量桥接和语义结构；全部视觉运动由现有 CSS 系统实现。移动端和 reduced-motion 使用 CSS 媒体查询降级。

**Tech Stack:** React 19、TypeScript、CSS Animation、Vitest、Testing Library。

---

### Task 1: 首屏交互结构

**Files:**
- Create: `frontend/src/components/EntryScreen.test.tsx`
- Modify: `frontend/src/components/EntryScreen.tsx`

- [ ] 写测试，验证舞台装饰存在、指针移动更新 CSS 变量、离开恢复中心、CTA 仍调用 `onStart`。
- [ ] 运行 `npm test -- EntryScreen.test.tsx`，确认测试因结构和行为尚未实现而失败。
- [ ] 使用 `requestAnimationFrame` 合并指针更新，仅在 fine pointer 且未请求 reduced motion 时启用。
- [ ] 再次运行聚焦测试并确认通过。

### Task 2: 首屏视觉动效

**Files:**
- Modify: `frontend/src/styles/components.css`

- [ ] 增加标题 reveal、背景光带、指针光场、轨道旋转、核心脉冲、标签漂浮、CTA 扫光和错峰入场。
- [ ] 保留现有断点，并在移动端降低装饰密度。
- [ ] 在 `prefers-reduced-motion: reduce` 中关闭持续动画和空间位移。

### Task 3: 验证

**Files:**
- Verify: `frontend/`

- [ ] 运行 `npm test`。
- [ ] 运行 `npm run build`。
- [ ] 在桌面和移动端检查首屏布局、动效、焦点状态与横向溢出。
