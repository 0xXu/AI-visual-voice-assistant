import { SendHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { TranscriptMessage } from "../app/session-reducer";

interface TranscriptDrawerProps {
  open: boolean;
  messages: TranscriptMessage[];
  protocolStage: number;
  onClose: () => void;
  onSendText: (text: string) => void;
}

function getMessageText(message: TranscriptMessage, protocolStage: number) {
  if (message.role === "user" && message.source === "voice" && protocolStage < 8) {
    return "语音提问";
  }

  return message.text;
}

export function TranscriptDrawer({
  open,
  messages,
  protocolStage,
  onClose,
  onSendText,
}: TranscriptDrawerProps) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    inputRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  const trimmedText = text.trim();

  return (
    <aside
      className="transcript-drawer"
      aria-label="完整对话记录"
      aria-modal="false"
    >
      <header className="transcript-drawer__header">
        <div>
          <span>对话记录</span>
          <strong>{messages.length} 条消息</strong>
        </div>
        <button type="button" aria-label="关闭记录" onClick={onClose}>
          <X size={18} />
        </button>
      </header>

      <div className="transcript-drawer__messages">
        {messages.length === 0 ? (
          <p className="transcript-empty">
            开始提问后，对话会出现在这里
          </p>
        ) : (
          messages.map((message) => (
            <article
              className="transcript-message"
              data-role={message.role}
              key={message.id}
            >
              <span>{message.role === "user" ? "你" : "AI"}</span>
              <p>{getMessageText(message, protocolStage)}</p>
            </article>
          ))
        )}
      </div>

      <form
        className="transcript-composer"
        onSubmit={(event) => {
          event.preventDefault();
          if (!trimmedText) {
            return;
          }
          onSendText(trimmedText);
          setText("");
        }}
      >
        <label>
          <span>文字提问</span>
          <textarea
            ref={inputRef}
            aria-label="文字提问"
            maxLength={2000}
            rows={3}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        <button type="submit" disabled={!trimmedText}>
          <SendHorizontal size={18} />
          发送
        </button>
      </form>
    </aside>
  );
}
