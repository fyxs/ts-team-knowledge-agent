import { useCallback, useRef, useState } from "react";
import { streamQuestion, type AgentEvent } from "../api/agent";

export type ToolStep = {
  name: string;
  label: string;
  detail?: string;
  status: "running" | "done";
};

export type ChatMessage =
  | { kind: "user"; id: number; content: string }
  | { kind: "process"; id: number; steps: ToolStep[]; running: boolean; startedAt: number; durationMs?: number }
  | { kind: "answer"; id: number; content: string; citations: string[]; steps: number; durationMs: number; retrieved: boolean }
  | { kind: "error"; id: number; message: string };

const TOOL_LABELS: Record<string, string> = {
  knowledge_search: "检索知识库",
  knowledge_read: "读取文档",
  knowledge_list: "列出文档",
  knowledge_status: "查看知识库状态",
  load_skill: "加载技能",
};

function describe(event: Extract<AgentEvent, { type: "tool_call" }>): string {
  const label = TOOL_LABELS[event.name] ?? event.name;
  const args = event.arguments ?? {};
  const hint = (args.query as string) || (args.path as string) || (args.prefix as string) || "";
  return hint ? `${label}：${hint}` : label;
}

export function useAgentChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const processIdRef = useRef<number | null>(null);
  const nextIdRef = useRef(1);
  const startedAtRef = useRef(0);

  const nextId = useCallback(() => nextIdRef.current++, []);

  // 注意：必须显式传入 processId。React 的函数式更新是延迟求值的，
  // 若在更新器里读取 ref，流结束较快的场景下 ref 已被清空，会匹配不到进程块。
  const updateProcess = useCallback(
    (processId: number | null, updater: (steps: ToolStep[], running: boolean) => Partial<ChatMessage>) => {
      if (processId === null) return;
      setMessages((current) =>
        current.map((message) => {
          if (message.kind !== "process" || message.id !== processId) return message;
          return { ...message, ...updater(message.steps, message.running) } as ChatMessage;
        }),
      );
    },
    [],
  );

  const handleEvent = useCallback(
    (event: AgentEvent) => {
      const processId = processIdRef.current;
      if (event.type === "start") {
        const id = nextId();
        processIdRef.current = id;
        startedAtRef.current = Date.now();
        setMessages((current) => [
          ...current,
          { kind: "process", id, steps: [], running: true, startedAt: Date.now() },
        ]);
        return;
      }
      if (event.type === "tool_call") {
        const step: ToolStep = { name: event.name, label: describe(event), status: "running" };
        updateProcess(processId, (steps) => ({ steps: [...steps, step] }));
        return;
      }
      if (event.type === "tool_result") {
        updateProcess(processId, (steps) => {
          const next = [...steps];
          for (let index = next.length - 1; index >= 0; index -= 1) {
            if (next[index].status === "running") {
              next[index] = { ...next[index], status: "done", detail: event.summary };
              break;
            }
          }
          return { steps: next };
        });
        return;
      }
      if (event.type === "answer") {
        const durationMs = Date.now() - startedAtRef.current;
        updateProcess(processId, () => ({ running: false, durationMs }));
        setMessages((current) => [
          ...current,
          {
            kind: "answer",
            id: nextId(),
            content: event.content,
            citations: event.citations ?? [],
            steps: event.steps ?? 0,
            durationMs,
            retrieved: event.retrieved !== false,
          },
        ]);
        return;
      }
      if (event.type === "error") {
        updateProcess(processId, () => ({ running: false }));
        setMessages((current) => [...current, { kind: "error", id: nextId(), message: event.error }]);
      }
    },
    [nextId, updateProcess],
  );

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || busy) return;
      setMessages((current) => [...current, { kind: "user", id: nextId(), content: trimmed }]);
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;
      let activeProcessId: number | null = null;
      try {
        await streamQuestion(trimmed, handleEvent, controller.signal);
      } catch (error) {
        const aborted = error instanceof DOMException && error.name === "AbortError";
        activeProcessId = processIdRef.current;
        if (!aborted) {
          updateProcess(activeProcessId, () => ({ running: false }));
          setMessages((current) => [
            ...current,
            { kind: "error", id: nextId(), message: error instanceof Error ? error.message : String(error) },
          ]);
        } else {
          updateProcess(activeProcessId, () => ({ running: false }));
        }
      } finally {
        setBusy(false);
        abortRef.current = null;
        processIdRef.current = null;
      }
    },
    [busy, handleEvent, nextId, updateProcess],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { messages, busy, send, stop };
}
