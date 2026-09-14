/**
 * 会话列表数据。
 *
 * 会话与历史消息接口尚未实现，这里先用固定数据把页面跑通；
 * 接口就绪后本模块换成 GET /api/v1/sessions，SessionSummary 与调用方不变。
 * 时间戳按模块加载时刻回推，保证分组标签始终落在今天 / 昨天 / 本周内。
 */

export type SessionSummary = {
  id: string;
  title: string;
  /** 最近一次活动时间（epoch ms）。 */
  updatedAt: number;
};

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

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
