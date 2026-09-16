export type AgentEvent =
  | { type: "start"; question: string }
  | { type: "tool_call"; name: string; arguments: Record<string, unknown>; step: number }
  | { type: "tool_result"; name: string; summary: string; step: number }
  | { type: "answer"; content: string; citations: string[]; sources?: AnswerSource[]; steps: number; retrieved?: boolean }
  | { type: "notice"; message: string }
  | { type: "error"; error: string; step?: number };

/** 一处命中：文档里的行号与该行片段。行号是全文坐标，界面据此跳到被引用的那一段。 */
export type SourceHit = { line: number; snippet: string };

/**
 * 结构化引用来源。`citations` 仍是不带结构的路径字符串（CLI 与评测按列表消费），
 * 界面要的标题与命中位置走这一份。
 */
export type AnswerSource = { path: string; title: string; hits: SourceHit[] };

/** 被引用文档的正文分页。字段与 `knowledge_read` 原语同名，两边语义一致。 */
export type KnowledgeDocument = {
  path: string;
  title: string;
  content: string;
  offset: number;
  returned_lines: number;
  total_lines: number;
  truncated: boolean;
};

export type ModelConfig = {
  provider: string;
  model: string;
  base_url: string;
  max_tokens: number;
  max_steps: number;
  scan_interval_minutes: number;
  api_key: string;
};

export type ModelConfigPatch = Partial<{
  provider: string;
  model: string;
  base_url: string;
  max_tokens: number;
  max_steps: number;
  scan_interval_minutes: number;
}>;

export type RunStatus = {
  running: boolean;
  started_at: string | null;
  last: {
    status?: string;
    scanned?: number;
    converted?: number;
    skipped?: number;
    failed?: number;
    indexed?: number;
    sync_status?: string;
    error?: string;
  } | null;
  report: Record<string, unknown> | null;
};

export type RepositoryResult = {
  status: string;
  commit: string | null;
  message: string | null;
};

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!response.ok) {
    throw new Error(text || `HTTP ${response.status}`);
  }
  return JSON.parse(text) as T;
}

export async function fetchModelConfig(): Promise<ModelConfig> {
  return readJson<ModelConfig>(await fetch("/api/v1/config"));
}

export async function saveModelConfig(patch: ModelConfigPatch): Promise<ModelConfig> {
  return readJson<ModelConfig>(
    await fetch("/api/v1/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  );
}

/** 流式提问：按事件回调逐步返回 Agent 的检索与作答过程。 */
export async function streamQuestion(
  question: string,
  sessionId: string,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId || undefined }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`问答接口返回 ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const line = block.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      const payload = line.slice(6).trim();
      if (!payload || payload === "[DONE]") continue;
      onEvent(JSON.parse(payload) as AgentEvent);
    }
  }
}

/** 读取被引用文档的正文。offset 是全文行号起点；来源阅读一次读全文，offset 只在需要跳读时用。 */
/**
 * 单次取回整篇正文的行数上限：来源阅读默认展示全文，与服务层 FULL_DOCUMENT_LIMIT 对齐。
 * 触到上限时后端会回 truncated，界面据此如实说明「只显示了前 N 行」。
 */
export const KNOWLEDGE_FULL_DOCUMENT_LINES = 100_000;

export async function fetchKnowledgeDocument(
  path: string,
  offset = 0,
  limit = KNOWLEDGE_FULL_DOCUMENT_LINES,
): Promise<KnowledgeDocument> {
  const params = new URLSearchParams({ path, offset: String(offset), limit: String(limit) });
  return readJson<KnowledgeDocument>(await fetch(`/api/v1/knowledge/document?${params.toString()}`));
}

/** 文档内相对资源的地址：由后端在同一套边界下读取，前端不直接拼知识仓路径。 */
export function knowledgeAssetUrl(path: string): string {
  return `/api/v1/knowledge/asset?${new URLSearchParams({ path }).toString()}`;
}

export async function fetchRunStatus(): Promise<RunStatus> {
  return readJson<RunStatus>(await fetch("/api/v1/run"));
}

export async function triggerRun(options?: { sync?: boolean; batch_size?: number }): Promise<{ status: string }> {
  return readJson<{ status: string }>(
    await fetch("/api/v1/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options ?? {}),
    }),
  );
}

export async function pullKnowledgeRepository(): Promise<RepositoryResult> {
  return readJson<RepositoryResult>(await fetch("/api/v1/repository/pull", { method: "POST" }));
}

export async function pushKnowledgeRepository(): Promise<RepositoryResult> {
  return readJson<RepositoryResult>(await fetch("/api/v1/repository/push", { method: "POST" }));
}
