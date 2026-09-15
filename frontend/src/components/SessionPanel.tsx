import type { SessionGroup } from "../hooks/useSessions";

type Props = {
  groups: SessionGroup[];
  total: number;
  activeId: string;
  query: string;
  onQueryChange: (value: string) => void;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onCollapse: () => void;
};

/** 历史会话面板：分组列表 + 搜索 + 新建 + 折叠，选中态用 accent 实心块表达。 */
export function SessionPanel({ groups, total, activeId, query, onQueryChange, onSelect, onCreate, onCollapse }: Props) {
  const matched = groups.reduce((sum, group) => sum + group.items.length, 0);

  return (
    <aside className="session-panel" aria-label="历史会话">
      <div className="session-head">
        <h2 className="session-head-title">历史会话</h2>
        <button type="button" className="session-new" onClick={onCreate}>
          新建
        </button>
        <button
          type="button"
          className="session-collapse"
          onClick={onCollapse}
          title="折叠历史面板"
          aria-label="折叠历史面板"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m14 6-6 6 6 6" />
          </svg>
        </button>
      </div>

      <div className="session-search">
        <input
          type="search"
          value={query}
          placeholder="搜索会话…"
          aria-label="搜索会话"
          onChange={(event) => onQueryChange(event.target.value)}
        />
      </div>

      <div className="session-list">
        {matched === 0 && <p className="session-empty">没有匹配的会话</p>}
        {groups.map((group) => (
          <div key={group.label}>
            <p className="session-group">{group.label}</p>
            {group.items.map((session) => (
              <button
                key={session.id}
                type="button"
                className="session-item"
                aria-current={session.id === activeId}
                onClick={() => onSelect(session.id)}
              >
                <span className="session-title">{session.title}</span>
                <span className="session-meta">{session.timeLabel}</span>
              </button>
            ))}
          </div>
        ))}
      </div>

      <div className="session-foot">
        <span>共 {total} 个会话</span>
        <span>本地保存</span>
      </div>
    </aside>
  );
}
