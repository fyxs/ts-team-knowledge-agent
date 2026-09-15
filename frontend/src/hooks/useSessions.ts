import { useCallback, useEffect, useMemo, useState } from "react";
import { createSession as createSessionRequest, listSessions, type SessionSummary } from "../api/sessions";

/** 会话标题上限；超出部分截断，避免超长问题把列表行撑开。 */
const TITLE_MAX = 40;

const PLACEHOLDER_TITLE = "新会话";

const DAY = 24 * 60 * 60 * 1000;

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

/** 列表项 = 会话元信息 + 已格式化的时间标签，展示组件不再做时间计算。 */
export type SessionListItem = SessionSummary & { timeLabel: string };

export type SessionGroup = {
  label: string;
  items: SessionListItem[];
};

function startOfDay(timestamp: number): number {
  const date = new Date(timestamp);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

function pad(value: number): string {
  return value < 10 ? `0${value}` : String(value);
}

/** 当天与昨天按语义显示，一周内显示星期，更早显示月/日。 */
function formatSessionTime(timestamp: number): string {
  const days = Math.round((startOfDay(Date.now()) - startOfDay(timestamp)) / DAY);
  const date = new Date(timestamp);
  if (days <= 0) return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  if (days === 1) return "昨天";
  if (days < 7) return WEEKDAYS[date.getDay()];
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

/** 按最近活动时间倒序分组；空分组不返回。 */
function buildGroups(sessions: SessionSummary[]): SessionGroup[] {
  const today = startOfDay(Date.now());
  const buckets = [
    { label: "今天", items: [] as SessionListItem[] },
    { label: "昨天", items: [] as SessionListItem[] },
    { label: "本周", items: [] as SessionListItem[] },
    { label: "更早", items: [] as SessionListItem[] },
  ];

  const sorted = [...sessions].sort((left, right) => right.updatedAt - left.updatedAt);
  for (const session of sorted) {
    const days = Math.round((today - startOfDay(session.updatedAt)) / DAY);
    const index = days <= 0 ? 0 : days === 1 ? 1 : days < 7 ? 2 : 3;
    buckets[index].items.push({ ...session, timeLabel: formatSessionTime(session.updatedAt) });
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
    refresh,
    collapse,
    expand,
  };
}
