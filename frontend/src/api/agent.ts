export type AgentEvent =
  | { type: "start"; question: string }
  | { type: "tool_call"; name: string; arguments: Record<string, unknown>; step: number }
  | { type: "tool_result"; name: string; summary: string; step: number }
  | { type: "answer"; content: string; citations: string[]; steps: number }
  | { type: "error"; error: string; step?: number };

export type ModelConfig = {
  provider: string;
  model: string;
  base_url: string;
  max_tokens: number;
  max_steps: number;
  api_key: string;
};

export type ModelConfigPatch = Partial<{
  provider: string;
  model: string;
  base_url: string;
  max_tokens: number;
  max_steps: number;
}>;

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
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
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
