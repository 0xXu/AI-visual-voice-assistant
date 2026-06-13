import { History, RotateCcw } from "lucide-react";
import type { TranscriptMessage } from "../app/session-reducer";
import type { TerminalStatus, UsageData } from "../protocol/messages";

interface SessionSummaryProps {
  terminalStatus: TerminalStatus | null;
  usage: UsageData | null;
  messages: TranscriptMessage[];
  onRestart: () => void;
  onOpenTranscript: () => void;
}

const terminalCopy: Record<TerminalStatus, string> = {
  stopped: "本次会话已结束",
  idle_timeout: "长时间没有收到输入，会话已自动结束",
  max_duration: "已达到单次会话最长时间",
  budget_exceeded: "已达到本次会话额度",
};

function formatDuration(durationMs: number) {
  const totalSeconds = Math.max(0, Math.round(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatNumber(value: number) {
  return value.toLocaleString("en-US");
}

export function SessionSummary({
  terminalStatus,
  usage,
  messages,
  onRestart,
  onOpenTranscript,
}: SessionSummaryProps) {
  const reason = terminalStatus ? terminalCopy[terminalStatus] : "会话已结束";

  return (
    <main className="summary-screen screen-enter">
      <section className="summary-panel">
        <p className="eyebrow">EchoSight 会话结果</p>
        <h1>{usage ? reason : "正在整理本次会话"}</h1>
        <p className="summary-description">
          {usage
            ? "本次实时视觉对话的数据已汇总，可查看用量或回到设备检测再次开始。"
            : "已停止采集媒体，正在等待服务端返回最终用量。"}
        </p>

        <div className="summary-metrics" aria-label="会话用量">
          <article>
            <span>持续时间</span>
            <strong>{usage ? formatDuration(usage.duration_ms) : "--:--"}</strong>
          </article>
          <article>
            <span>首响应</span>
            <strong>
              {usage?.first_response_latency_ms == null
                ? "未产生回答"
                : `${formatNumber(usage.first_response_latency_ms)} ms`}
            </strong>
          </article>
          <article>
            <span>Total tokens</span>
            <strong>{usage ? formatNumber(usage.total_tokens) : "--"}</strong>
          </article>
          <article>
            <span>Input / Output</span>
            <strong>
              {usage
                ? `${formatNumber(usage.input_tokens)} / ${formatNumber(
                    usage.output_tokens,
                  )}`
                : "--"}
            </strong>
          </article>
          <article>
            <span>视频帧</span>
            <strong>{usage ? formatNumber(usage.video_frames) : "--"}</strong>
          </article>
          <article>
            <span>替换帧</span>
            <strong>
              {usage ? formatNumber(usage.video_replaced_frames) : "--"}
            </strong>
          </article>
        </div>

        <div className="summary-actions">
          <button type="button" onClick={onRestart}>
            <RotateCcw size={18} />
            再次开始
          </button>
          <button type="button" onClick={onOpenTranscript}>
            <History size={18} />
            查看对话记录
          </button>
        </div>

        <p className="summary-footnote">
          本地记录包含 {messages.length} 条消息，媒体内容不会保存在浏览器代码中。
        </p>
      </section>
    </main>
  );
}
