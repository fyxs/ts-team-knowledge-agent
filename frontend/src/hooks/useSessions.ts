import { useCallback, useMemo, useState } from "react";
import { groupSessions, SESSIONS_SEED, type SessionGroup, type SessionSummary } from "../data/sessions";

/** 会话标题上限；超出部分截断，避免超长问题把列表行撑开。 */
const TITLE_MAX = 40;

const PLACEHOLDER_TITLE = "新会话";

let seq = 0;

/** 历史会话列表状态：选中、搜索、新建，以及会话元信息的就地更新。 */
export function useSessions() {
  const [sessions, setSessions] = useState<SessionSummary[]>(SESSIONS_SEED);
  const [activeId, setActiveId] = useState<string>(SESSIONS_SEED[0]?.id ?? "");
  const [query, setQuery] = useState("");

  const groups: SessionGroup[] = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    const matched =
      keyword === ""
        ? sessions
        : sessions.filter((session) => session.title.toLowerCase().includes(keyword));
    return groupSessions(matched);
  }, [sessions, query]);

  const createSession = useCallback(() => {
    seq += 1;
    const session: SessionSummary = {
      id: `session-${Date.now().toString(36)}-${seq}`,
      title: PLACEHOLDER_TITLE,
      updatedAt: Date.now(),
    };
    setSessions((current) => [session, ...current]);
    setActiveId(session.id);
    setQuery("");
  }, []);

  const selectSession = useCallback((id: string) => {
    setActiveId(id);
  }, []);

  /** 会话产生新消息时调用：刷新活动时间，并在首次提问后把占位标题换成问题。 */
  const touchSession = useCallback((id: string, question?: string) => {
    const title = question?.trim().replace(/\s+/g, " ");
    setSessions((current) =>
      current.map((session) => {
        if (session.id !== id) return session;
        const renamed =
          title && session.title === PLACEHOLDER_TITLE
            ? { title: title.length > TITLE_MAX ? `${title.slice(0, TITLE_MAX)}…` : title }
            : {};
        return { ...session, ...renamed, updatedAt: Date.now() };
      }),
    );
  }, []);

  return {
    groups,
    total: sessions.length,
    activeId,
    query,
    setQuery,
    createSession,
    selectSession,
    touchSession,
  };
}
