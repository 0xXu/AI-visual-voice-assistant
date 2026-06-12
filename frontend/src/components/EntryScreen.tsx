import { ArrowRight, Camera, Mic } from "lucide-react";

interface EntryScreenProps {
  onStart: () => void;
}

export function EntryScreen({ onStart }: EntryScreenProps) {
  return (
    <main className="entry-screen screen-enter">
      <div className="atmosphere atmosphere--primary" aria-hidden="true" />
      <div className="atmosphere atmosphere--secondary" aria-hidden="true" />
      <div className="entry-grid" aria-hidden="true" />

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
          让 AI
          <span>看见你所看见的</span>
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
        <div className="entry-orbit__core">
          <span />
        </div>
        <div className="entry-orbit__label entry-orbit__label--vision">
          <Camera size={15} />
          视觉理解
        </div>
        <div className="entry-orbit__label entry-orbit__label--voice">
          <Mic size={15} />
          自然语音
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
