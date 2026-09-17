import { useCallback, useEffect, useRef, useState } from "react";
import { SESSION_TITLE_MAX } from "../api/sessions";
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
  onRename: (id: string, title: string) => void;
  onRequestDelete: (id: string) => void;
};

/** 历史会话面板：单行列表（会话名 + 更多菜单）+ 搜索 + 新建 + 折叠，选中态用 accent 实心块表达。 */
export function SessionPanel({
  groups,
  total,
  activeId,
  query,
  onQueryChange,
  onSelect,
  onCreate,
  onCollapse,
  onRename,
  onRequestDelete,
}: Props) {
  const matched = groups.reduce((sum, group) => sum + group.items.length, 0);

  /** 打开菜单的行；同一时刻只允许一个。 */
  const [menuId, setMenuId] = useState("");
  /** 正在重命名的行：记下原名，失焦时用它判断该不该回退。 */
  const [editing, setEditing] = useState<{ id: string; original: string } | null>(null);
  const [draft, setDraft] = useState("");
  const editRef = useRef<HTMLInputElement>(null);
  /** Esc 取消时置位，让随后的失焦跳过提交。 */
  const skipCommit = useRef(false);

  // 进入重命名即聚焦并全选：改名多半是想换掉整个标题，而不是接着往后补。
  useEffect(() => {
    if (!editing) return;
    editRef.current?.focus();
    editRef.current?.select();
  }, [editing]);

  // 点空白处或按 Esc 收起菜单。
  useEffect(() => {
    if (menuId === "") return;
    const close = () => setMenuId("");
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuId("");
    };
    document.addEventListener("click", close);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuId]);

  const closeEditor = useCallback(() => {
    setEditing(null);
    setDraft("");
  }, []);

  /** 唯一的提交路径：Enter 只是让输入框失焦，保存逻辑都走失焦。 */
  const commitRename = useCallback(() => {
    if (!editing) return;
    const next = draft.trim();
    // 清空后失焦不保存：静默回退原名。空标题没有意义，留个空行更糟。
    if (next !== "" && next !== editing.original) onRename(editing.id, next);
    closeEditor();
  }, [closeEditor, draft, editing, onRename]);

  const startRename = useCallback((id: string, title: string) => {
    setMenuId("");
    setDraft(title);
    setEditing({ id, original: title });
  }, []);

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
            {group.items.map((session) =>
              editing?.id === session.id ? (
                <div className="session-row" key={session.id}>
                  <input
                    ref={editRef}
                    className="session-edit-input"
                    value={draft}
                    maxLength={SESSION_TITLE_MAX}
                    aria-label="会话名称"
                    onChange={(event) => setDraft(event.target.value)}
                    onBlur={() => {
                      if (skipCommit.current) {
                        skipCommit.current = false;
                        closeEditor();
                        return;
                      }
                      commitRename();
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        event.currentTarget.blur();
                      } else if (event.key === "Escape") {
                        event.preventDefault();
                        skipCommit.current = true;
                        event.currentTarget.blur();
                      }
                    }}
                  />
                </div>
              ) : (
                <div className="session-row" key={session.id}>
                  <button
                    type="button"
                    className="session-item"
                    aria-current={session.id === activeId}
                    onClick={() => onSelect(session.id)}
                  >
                    <span className="session-title">{session.title}</span>
                  </button>

                  <div className="session-actions">
                    <button
                      type="button"
                      className="session-action"
                      title="更多操作"
                      aria-label="更多操作"
                      aria-haspopup="menu"
                      aria-expanded={menuId === session.id}
                      onClick={(event) => {
                        // 挡住冒泡，否则文档上的关闭监听会立刻把它收掉。
                        event.stopPropagation();
                        setMenuId(menuId === session.id ? "" : session.id);
                      }}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <circle cx="5.5" cy="12" r="1.7" />
                        <circle cx="12" cy="12" r="1.7" />
                        <circle cx="18.5" cy="12" r="1.7" />
                      </svg>
                    </button>
                  </div>

                  {menuId === session.id && (
                    <div className="session-menu" role="menu">
                      <button
                        type="button"
                        role="menuitem"
                        className="session-menu-item"
                        onClick={() => startRename(session.id, session.title)}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M4 20l1.2-4.2L16.4 4.6a2.2 2.2 0 0 1 3.1 3.1L8.3 18.9 4 20Z" />
                          <path d="M14.8 6.2l3.1 3.1" />
                        </svg>
                        重命名
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        className="session-menu-item is-danger"
                        onClick={() => {
                          setMenuId("");
                          onRequestDelete(session.id);
                        }}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M4.5 7h15" />
                          <path d="M9.5 7V5.6c0-.9.7-1.6 1.6-1.6h1.8c.9 0 1.6.7 1.6 1.6V7" />
                          <path d="M6.6 7l.85 12.2c.06.87.79 1.55 1.66 1.55h5.78c.87 0 1.6-.68 1.66-1.55L17.4 7" />
                        </svg>
                        删除
                      </button>
                    </div>
                  )}
                </div>
              ),
            )}
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
