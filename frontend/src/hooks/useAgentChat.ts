import { useCallback, useEffect, useRef, useState } from "react";
import { streamQuestion, type AgentEvent } from "../api/agent";
import type { AnswerSource } from "../api/agent";
import { fetchSessionMessages, type StoredMessage } from "../api/sessions";

export type ToolStep = {
  name: string;
  label: string;
  detail?: string;
  status: "running" | "done";
};

export type ChatMessage =
  | { kind: "user"; id: number; content: string }
  | { kind: "process"; id: number; steps: ToolStep[]; running: boolean; startedAt: number; durationMs?: number }
  | {
      kind: "answer";
      id: number;
      content: string;
      citations: string[];
      /** 结构化引用来源：标题 + 命中行号。界面用它打开来源阅读层。 */
      sources: AnswerSource[];
      steps: number;
      durationMs: number;
      retrieved: boolean;
    }
  | { kind: "error"; id: number; message: string };

const TOOL_LABELS: Record<string, string> = {
  knowledge_search: "检索知识库",
  knowledge_read: "读取文档",
  knowledge_list: "列出文档",
  knowledge_status: "查看知识库状态",
  load_skill: "加载技能",
};

/** 把服务端保存的消息映射为界面消息；历史 id 取负数避免与实时消息的自增 id 冲突。 */
function toChatMessages(stored: StoredMessage[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  for (const item of stored) {
    if (item.kind === "user") {
      result.push({ kind: "user", id: -item.id, content: item.content ?? "" });
      continue;
    }
    if (item.kind === "answer") {
      result.push({
        kind: "answer",
        id: -item.id,
        content: item.content ?? "",
        citations: item.citations ?? [],
        sources: item.sources ?? [],
        steps: typeof item.steps === "number" ? item.steps : 0,
        durationMs: 0,
        retrieved: item.retrieved !== false,
      });
      continue;
    }
    if (item.kind === "error") {
      result.push({ kind: "error", id: -item.id, message: item.message ?? "回答失败" });
      continue;
    }
    if (item.kind === "process") {
      const steps = Array.isArray(item.steps) ? item.steps : [];
      result.push({
        kind: "process",
        id: -item.id,
        steps: steps.map((step) => ({
          name: step.name,
          label: TOOL_LABELS[step.name] ?? step.name,
          detail: step.detail,
          status: "done" as const,
        })),
        running: false,
        startedAt: 0,
      });
    }
  }
  return result;
}

function describe(event: Extract<AgentEvent, { type: "tool_call" }>): string {
  const label = TOOL_LABELS[event.name] ?? event.name;
  const args = event.arguments ?? {};
  const hint = (args.query as string) || (args.path as string) || (args.prefix as string) || "";
  return hint ? `${label}：${hint}` : label;
}

/** 消息 id 全局递增：多条会话的消息可能同时挂载，避免 id 撞车。 */
let nextMessageId = 1;

const EMPTY_MESSAGES: ChatMessage[] = [];

/**
 * 对话状态机。消息按会话分开存放，切换会话只换显示的那一份；
 * 在途的流始终写回它开始时所属的会话。
 */
export function useAgentChat(sessionId: string) {
  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessage[]>>({});
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const processIdRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);

  const messages = messagesBySession[sessionId] ?? EMPTY_MESSAGES;
  const hydratedRef = useRef<Set<string>>(new Set());

  // 切换会话时按需拉取一次历史；已加载过的会话不再覆盖，避免抹掉在途或刚产生的消息。
  useEffect(() => {
    if (!sessionId || hydratedRef.current.has(sessionId)) return;
    let cancelled = false;
    void (async () => {
      try {
        const stored = await fetchSessionMessages(sessionId);
        if (cancelled) return;
        hydratedRef.current.add(sessionId);
        setMessagesBySession((current) => ({ ...current, [sessionId]: toChatMessages(stored.messages) }));
      } catch {
        // 历史加载失败不阻塞提问：保持空记录，用户继续提问即可。
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const append = useCallback((target: string, message: ChatMessage) => {
    setMessagesBySession((current) => ({
      ...current,
      [target]: [...(current[target] ?? []), message],
    }));
  }, []);

  // 注意：必须显式传入 processId。React 的函数式更新是延迟求值的，
  // 若在更新器里读取 ref，流结束较快的场景下 ref 已被清空，会匹配不到进程块。
  const updateProcess = useCallback(
    (
      target: string,
      processId: number | null,
      updater: (steps: ToolStep[], running: boolean) => Partial<ChatMessage>,
    ) => {
      if (processId === null) return;
      setMessagesBySession((current) => ({
        ...current,
        [target]: (current[target] ?? []).map((message) => {
          if (message.kind !== "process" || message.id !== processId) return message;
          return { ...message, ...updater(message.steps, message.running) } as ChatMessage;
        }),
      }));
    },
    [],
  );

  const handleEvent = useCallback(
    (target: string, event: AgentEvent) => {
      const processId = processIdRef.current;
      if (event.type === "start") {
        const id = nextMessageId++;
        processIdRef.current = id;
        startedAtRef.current = Date.now();
        append(target, { kind: "process", id, steps: [], running: true, startedAt: Date.now() });
        return;
      }
      if (event.type === "tool_call") {
        const step: ToolStep = { name: event.name, label: describe(event), status: "running" };
        updateProcess(target, processId, (steps) => ({ steps: [...steps, step] }));
        return;
      }
      if (event.type === "tool_result") {
        updateProcess(target, processId, (steps) => {
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
        updateProcess(target, processId, () => ({ running: false, durationMs }));
        append(target, {
          kind: "answer",
          id: nextMessageId++,
          content: event.content,
          citations: event.citations ?? [],
          sources: event.sources ?? [],
          steps: event.steps ?? 0,
          durationMs,
          retrieved: event.retrieved !== false,
        });
        return;
      }
      if (event.type === "error") {
        updateProcess(target, processId, () => ({ running: false }));
        append(target, { kind: "error", id: nextMessageId++, message: event.error });
      }
    },
    [append, updateProcess],
  );

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || busy) return;
      const target = sessionId;
      append(target, { kind: "user", id: nextMessageId++, content: trimmed });
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;
      let activeProcessId: number | null = null;
      try {
        await streamQuestion(trimmed, target, (event) => handleEvent(target, event), controller.signal);
      } catch (error) {
        const aborted = error instanceof DOMException && error.name === "AbortError";
        activeProcessId = processIdRef.current;
        updateProcess(target, activeProcessId, () => ({ running: false }));
        if (!aborted) {
          append(target, {
            kind: "error",
            id: nextMessageId++,
            message: error instanceof Error ? error.message : String(error),
          });
        }
      } finally {
        setBusy(false);
        abortRef.current = null;
        processIdRef.current = null;
      }
    },
    [busy, handleEvent, sessionId, append, updateProcess],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // 切换会话时中止在途的流：否则「停止」按钮会出现在另一条会话里，语义不清。
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, [sessionId]);

  return { messages, busy, send, stop };
}
