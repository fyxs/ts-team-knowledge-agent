/** 会话与历史消息接口。数据存放在本机 SQLite，不进共享知识仓。 */

export type SessionSummary = {
  id: string;
  title: string;
  /** 最近一次活动时间（epoch ms），前端据此分组。 */
  updatedAt: number;
};

export type StoredStep = { name: string; detail?: string };

export type StoredMessage = {
  id: number;
  kind: string;
  content?: string;
  citations?: string[];
  retrieved?: boolean;
  steps?: number | StoredStep[];
  message?: string;
};

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
  return JSON.parse(text) as T;
}

export async function listSessions(): Promise<SessionSummary[]> {
  const data = await readJson<{ sessions?: SessionSummary[] }>(await fetch("/api/v1/sessions"));
  return data.sessions ?? [];
}

export async function createSession(): Promise<SessionSummary> {
  return readJson<SessionSummary>(await fetch("/api/v1/sessions", { method: "POST" }));
}

export async function fetchSessionMessages(
  sessionId: string,
): Promise<{ session: SessionSummary | null; messages: StoredMessage[] }> {
  const data = await readJson<{ session?: SessionSummary; messages?: StoredMessage[] }>(
    await fetch(`/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`),
  );
  return { session: data.session ?? null, messages: data.messages ?? [] };
}
