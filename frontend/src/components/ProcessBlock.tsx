import { useEffect, useState } from "react";
import type { ToolStep } from "../hooks/useAgentChat";

type Props = {
  steps: ToolStep[];
  running: boolean;
  durationMs?: number;
};

/** 把一轮问答中的多次工具调用收进一个可折叠区块，避免刷屏。 */
export function ProcessBlock({ steps, running, durationMs }: Props) {
  const [open, setOpen] = useState(running);

  useEffect(() => {
    setOpen(running);
  }, [running]);

  const seconds = durationMs ? Math.max(1, Math.round(durationMs / 1000)) : null;
  const summary = running
    ? `正在检索知识库…（已完成 ${steps.filter((step) => step.status === "done").length} 步）`
    : `检索过程 · ${steps.length} 步${seconds ? ` · ${seconds}s` : ""}`;

  return (
    <details className="process" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        {running && <span className="spinner" aria-hidden="true" />}
        <span className="process-summary">{summary}</span>
      </summary>
      <ol className="process-steps">
        {steps.map((step, index) => (
          <li key={`${step.name}-${index}`} className={step.status === "done" ? "step-done" : "step-running"}>
            <span className="step-label">{step.label}</span>
            {step.detail && <span className="step-detail">{step.detail}</span>}
          </li>
        ))}
      </ol>
    </details>
  );
}
