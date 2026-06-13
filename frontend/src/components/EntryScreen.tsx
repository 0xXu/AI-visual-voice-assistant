import { useRef } from "react";
import { ArrowRight, Camera, Mic } from "lucide-react";

interface EntryScreenProps {
  onStart: () => void;
}

export function EntryScreen({ onStart }: EntryScreenProps) {
  const stageRef = useRef<HTMLElement | null>(null);
  const pointerFramePending = useRef(false);
  const pendingPointer = useRef({ x: 50, y: 50 });

  const updatePointer = (x: number, y: number) => {
    const stage = stageRef.current;
    if (!stage) {
      return;
    }

    stage.style.setProperty("--entry-pointer-x", `${x}%`);
    stage.style.setProperty("--entry-pointer-y", `${y}%`);
    stage.style.setProperty("--entry-shift-x", `${(x - 50) * 0.12}px`);
    stage.style.setProperty("--entry-shift-y", `${(y - 50) * 0.08}px`);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLElement>) => {
    if (
      !window.matchMedia("(pointer: fine)").matches ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }

    const bounds = event.currentTarget.getBoundingClientRect();
    pendingPointer.current = {
      x: Math.max(0, Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100)),
      y: Math.max(0, Math.min(100, ((event.clientY - bounds.top) / bounds.height) * 100)),
    };

    if (pointerFramePending.current) {
      return;
    }

    pointerFramePending.current = true;
    window.requestAnimationFrame(() => {
      pointerFramePending.current = false;
      updatePointer(pendingPointer.current.x, pendingPointer.current.y);
    });
  };

  return (
    <main
      ref={stageRef}
      className="entry-screen screen-enter"
      style={
        {
          "--entry-pointer-x": "50%",
          "--entry-pointer-y": "50%",
          "--entry-shift-x": "0px",
          "--entry-shift-y": "0px",
        } as React.CSSProperties
      }
      onPointerMove={handlePointerMove}
      onPointerLeave={() => updatePointer(50, 50)}
    >
      <div className="atmosphere atmosphere--primary" aria-hidden="true" />
      <div className="atmosphere atmosphere--secondary" aria-hidden="true" />
      <div className="entry-grid" aria-hidden="true" />
      <div className="entry-stage__beam" aria-hidden="true" />
      <div className="entry-stage__grain" aria-hidden="true" />

      <header className="entry-header">
        <a className="brand-mark" href="/" aria-label="EchoSight 首页">
          <span className="brand-mark__signal" aria-hidden="true" />
          <span>EchoSight</span>
        </a>
        <span className="entry-header__status">
          <span aria-hidden="true" />
          Gemini Live
        </span>
      </header>

      <section className="entry-content" aria-labelledby="entry-title">
        <p className="eyebrow">
          <span className="eyebrow__icon" aria-hidden="true">
            <Camera size={14} strokeWidth={2} />
          </span>
          EchoSight 实时视觉对话
        </p>

        <h1 id="entry-title">
          <span className="entry-title__line">让 AI</span>
          <span className="entry-title__accent">看见你所看见的</span>
        </h1>

        <p className="entry-description">
          打开摄像头和麦克风，直接询问眼前的物品、环境与操作步骤。
          无需拍照上传，边看边聊。
        </p>

        <div className="entry-actions">
          <button className="button-primary" type="button" onClick={onStart}>
            开始视觉对话
            <ArrowRight size={18} aria-hidden="true" />
          </button>
          <span className="entry-actions__hint">下一步将检测摄像头与麦克风</span>
        </div>

        <p className="privacy-note">
          <span className="privacy-note__icons" aria-hidden="true">
            <Camera size={15} />
            <Mic size={15} />
          </span>
          设备内容仅在会话期间用于实时回答
        </p>
      </section>

      <aside className="entry-orbit" aria-hidden="true">
        <div className="entry-orbit__ring entry-orbit__ring--outer" />
        <div className="entry-orbit__ring entry-orbit__ring--inner" />
        <div className="entry-orbit__ticks" />
        <div className="entry-orbit__scan" />
        <div className="entry-orbit__core">
          <span />
        </div>
        <div className="entry-orbit__carrier entry-orbit__carrier--vision">
          <div className="entry-orbit__satellite-anchor">
            <span className="entry-orbit__node" />
            <div className="entry-orbit__satellite">
              <Camera size={15} />
              <span>视觉理解</span>
            </div>
          </div>
        </div>
        <div className="entry-orbit__carrier entry-orbit__carrier--voice">
          <div className="entry-orbit__satellite-anchor">
            <span className="entry-orbit__node" />
            <div className="entry-orbit__satellite">
              <Mic size={15} />
              <span>自然语音</span>
            </div>
          </div>
        </div>
      </aside>

      <footer className="entry-footer">
        <span>视觉理解</span>
        <span aria-hidden="true">·</span>
        <span>自然语音</span>
        <span aria-hidden="true">·</span>
        <span>实时响应</span>
      </footer>
    </main>
  );
}
