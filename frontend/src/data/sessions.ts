/**
 * 历史会话的本地静态数据。
 *
 * 会话与历史消息的接口尚未实现，这里先用固定数据把页面跑通；接口就绪后
 * 本模块整体替换为 fetchSessions() / fetchSessionMessages()，对外类型不变。
 * 时间戳按模块加载时刻回推，保证分组标签始终落在今天 / 昨天 / 本周内。
 */

export type SessionSummary = {
  id: string;
  title: string;
  /** 最近一次活动时间（epoch ms）。 */
  updatedAt: number;
};

export type SessionGroup = {
  label: string;
  items: SessionSummary[];
};

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

const loadedAt = Date.now();

export const SESSIONS_SEED: SessionSummary[] = [
  { id: "env-and-config", title: "前端编码规范里对环境变量有什么要求？", updatedAt: loadedAt - 24 * MINUTE },
  { id: "component-library", title: "团队移动端组件库的架构是怎样的？", updatedAt: loadedAt - 3 * HOUR },
  { id: "mineru-failures", title: "MinerU 转换失败有哪些可重试的情况", updatedAt: loadedAt - 26 * HOUR },
  { id: "repo-sync", title: "共享知识仓的拉取与推送流程", updatedAt: loadedAt - 30 * HOUR },
  { id: "scan-schedule", title: "扫描间隔与计划任务怎么配", updatedAt: loadedAt - 3 * DAY },
  { id: "citation-empty", title: "引用来源为空是怎么回事", updatedAt: loadedAt - 4 * DAY },
  { id: "quality-gate", title: "转换质量门禁的判定标准", updatedAt: loadedAt - 12 * DAY },
];

function startOfDay(timestamp: number): number {
  const date = new Date(timestamp);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

function pad(value: number): string {
  return value < 10 ? `0${value}` : String(value);
}

/** 列表时间：当天与昨天按语义显示，一周内显示星期，更早显示月/日。 */
export function formatSessionTime(timestamp: number): string {
  const days = Math.round((startOfDay(Date.now()) - startOfDay(timestamp)) / DAY);
  const date = new Date(timestamp);
  if (days <= 0) return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  if (days === 1) return "昨天";
  if (days < 7) return WEEKDAYS[date.getDay()];
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

/** 按最近活动时间倒序分组；空分组不返回。 */
export function groupSessions(sessions: SessionSummary[]): SessionGroup[] {
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
