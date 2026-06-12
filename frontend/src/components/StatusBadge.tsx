import type { SessionPhase } from "../app/session-reducer";

const phaseText: Record<SessionPhase, string> = {
  idle: "准备开始",
  "device-check": "检查设备",
  connecting: "正在连接",
  listening: "正在聆听",
  thinking: "正在思考",
  speaking: "正在回答",
  recovering: "正在恢复",
  ending: "正在整理",
  ended: "会话结束",
};

interface StatusBadgeProps {
  phase: SessionPhase;
}

export function StatusBadge({ phase }: StatusBadgeProps) {
  return (
    <div className="status-badge" data-phase={phase}>
      <span aria-hidden="true" />
      {phaseText[phase]}
    </div>
  );
}
