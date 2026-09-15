import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createSession as createSessionRequest,
  deleteSession as deleteSessionRequest,
  listSessions,
  renameSession as renameSessionRequest,
  type SessionSummary,
} from "../api/sessions";

/** 会话标题上限；超出部分截断，避免超长问题把列表行撑开。 */
const TITLE_MAX = 20;

const PLACEHOLDER_TITLE = "新会话";

const DAY = 24 * 60 * 60 * 1000;

export type SessionGroup = {
  label: string;
  items: SessionSummary[];
};

function startOfDay(timestamp: number): number {
  const date = new Date(timestamp);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

/** 按最近活动时间倒序分组；空分组不返回。 */
function buildGroups(sessions: SessionSummary[]): SessionGroup[] {
  const today = startOfDay(Date.now());
  const buckets: SessionGroup[] = [
    { label: "今天", items: [] },
    { label: "昨天", items: [] },
    { label: "本周", items: [] },
    { label: "更早", items: [] },
  ];

  const sorted = [...sessions].sort((left, right) => right.updatedAt - left.updatedAt);
  for (const session of sorted) {
    const days = Math.round((today - startOfDay(session.updatedAt)) / DAY);
    const index = days <= 0 ? 0 : days === 1 ? 1 : days < 7 ? 2 : 3;
    buckets[index].items.push(session);
  }

  return buckets.filter((bucket) => bucket.items.length > 0);
}

/** 历史会话列表状态：选中、搜索、新建、折叠，以及会话元信息的就地更新。 */
export function useSessions() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [query, setQuery] = useState("");
  /** 宽屏下收起会话列，把宽度让回对话面板；窄屏的抽屉开关另由 sessionsOpen 管理。 */
  const [collapsed, setCollapsed] = useState(false);

  const groups = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    const matched =
      keyword === ""
        ? sessions
        : sessions.filter((session) => session.title.toLowerCase().includes(keyword));
    return buildGroups(matched);
  }, [sessions, query]);

  /** 重新拉取会话列表：一轮问答结束后调用，同步标题与活动时间。 */
  const refresh = useCallback(async () => {
    const items = await listSessions();
    setSessions(items);
    setActiveId((current) => (current && items.some((item) => item.id === current) ? current : items[0]?.id ?? ""));
    return items;
  }, []);

  // 首次进入：拉取本机会话列表；一条都没有时创建一个空会话，避免界面停在无会话态。
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        let items = await listSessions();
        if (items.length === 0) {
          const created = await createSessionRequest();
          items = [created];
        }
        if (cancelled) return;
        setSessions(items);
        setActiveId(items[0]?.id ?? "");
      } catch {
        // 接口不可用时保持空列表：面板显示空态，不伪造历史会话。
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const createSession = useCallback(async () => {
    const created = await createSessionRequest();
    setSessions((current) => [created, ...current.filter((item) => item.id !== created.id)]);
    setActiveId(created.id);
    setQuery("");
  }, []);

  const selectSession = useCallback((id: string) => {
    setActiveId(id);
  }, []);

  /** 会话产生新消息时调用：就地刷新活动时间；标题以服务端为准，随后由 refresh 校正。 */
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

  /** 重命名：空标题不接受（是否回退由调用方决定），超长按上限截断。 */
  const renameSession = useCallback(async (id: string, title: string) => {
    const trimmed = title.trim();
    if (trimmed === "") return;
    const capped = trimmed.length > TITLE_MAX ? trimmed.slice(0, TITLE_MAX) : trimmed;
    const updated = await renameSessionRequest(id, capped);
    setSessions((current) => current.map((session) => (session.id === id ? updated : session)));
  }, []);

  /** 删除：删掉的若是当前会话，接管它原位置上的下一条，没有则取上一条；全删光则回到空态。 */
  const removeSession = useCallback(
    async (id: string) => {
      await deleteSessionRequest(id);
      const rest = sessions.filter((session) => session.id !== id);
      if (id !== activeId) {
        setSessions(rest);
        return;
      }
      const index = sessions.findIndex((session) => session.id === id);
      if (rest.length > 0) {
        setSessions(rest);
        setActiveId(rest[Math.min(index, rest.length - 1)]?.id ?? "");
        return;
      }
      // 删光后立刻补一个空会话：否则之后每条提问都会被服务端各建成一个会话，列表与对话区对不上。
      const created = await createSessionRequest();
      setSessions([created]);
      setActiveId(created.id);
    },
    [sessions, activeId],
  );

  const collapse = useCallback(() => {
    setCollapsed(true);
  }, []);

  const expand = useCallback(() => {
    setCollapsed(false);
  }, []);

  return {
    groups,
    total: sessions.length,
    activeId,
    query,
    setQuery,
    collapsed,
    createSession,
    selectSession,
    touchSession,
    renameSession,
    removeSession,
    refresh,
    collapse,
    expand,
  };
}
