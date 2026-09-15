import { useCallback, useMemo, useState } from "react";
import { Composer } from "./components/Composer";
import { FocusView } from "./components/FocusView";
import { MessageList } from "./components/MessageList";
import { Modal } from "./components/Modal";
import { SessionDock } from "./components/SessionDock";
import { SessionPanel } from "./components/SessionPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { useAgentChat } from "./hooks/useAgentChat";
import { useSessions } from "./hooks/useSessions";
import { useTheme } from "./hooks/useTheme";

export default function App() {
  const { groups, total, activeId, query, setQuery, collapsed, createSession, selectSession, touchSession, renameSession, removeSession, refresh, collapse, expand } =
    useSessions();
  const { messages, busy, send, stop } = useAgentChat(activeId);
  const { theme, toggle } = useTheme();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  /** 待确认删除的会话 id。确认框放在 App 层：面板是 overflow:hidden，遮罩放里面会被裁掉。 */
  const [pendingDeleteId, setPendingDeleteId] = useState("");

  const pendingDelete = useMemo(() => {
    if (pendingDeleteId === "") return null;
    for (const group of groups) {
      const session = group.items.find((item) => item.id === pendingDeleteId);
      if (session) return session;
    }
    return null;
  }, [groups, pendingDeleteId]);

  const handleConfirmDelete = useCallback(() => {
    const id = pendingDeleteId;
    setPendingDeleteId("");
    void removeSession(id);
  }, [pendingDeleteId, removeSession]);

  /** 正在集中阅读的那条答案 id。范围就是一条答案，不涉及其它回答块。 */
  const [focusedId, setFocusedId] = useState<number | null>(null);

  const focused = useMemo(() => {
    if (focusedId === null) return null;
    const index = messages.findIndex((message) => message.id === focusedId);
    const message = index >= 0 ? messages[index] : undefined;
    if (!message || message.kind !== "answer") return null;
    // 头部显示这个问题：往上找最近的一条用户消息，比只写「集中阅读」更能说明在看什么。
    let question = "";
    for (let i = index - 1; i >= 0; i -= 1) {
      const earlier = messages[i];
      if (earlier.kind === "user") {
        question = earlier.content;
        break;
      }
    }
    return { message, question };
  }, [focusedId, messages]);

  const handleSend = useCallback(
    (question: string) => {
      touchSession(activeId, question);
      void send(question).finally(() => {
        // 一轮结束后刷新列表：服务端会据首条提问生成标题并更新活动时间。
        void refresh();
      });
    },
    [activeId, send, touchSession, refresh],
  );

  const handleCreate = useCallback(() => {
    createSession();
    setSessionsOpen(false);
  }, [createSession]);

  const handleRename = useCallback(
    (id: string, title: string) => {
      void renameSession(id, title);
    },
    [renameSession],
  );

  const handleSelect = useCallback(
    (id: string) => {
      selectSession(id);
      setSessionsOpen(false);
    },
    [selectSession],
  );

  const shellClass = ["app-shell", collapsed ? "is-collapsed" : "", sessionsOpen ? "sessions-open" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <main className={shellClass}>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">TS</div>
          <div>
            <strong>TS 团队知识 Agent</strong>
            <span>本地优先 · 基于团队共享知识库作答</span>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="connection-status"><i /> {busy ? "正在作答" : "就绪"}</span>
          <button type="button" className="session-toggle" onClick={() => setSessionsOpen(true)}>
            历史会话
          </button>
          <button type="button" className="theme-toggle" onClick={toggle} aria-label="切换主题">
            {theme === "dark" ? "浅色" : "深色"}
          </button>
          <button type="button" className="settings-button" onClick={() => setSettingsOpen(true)}>
            设置
          </button>
        </div>
      </header>

      <section className="chat-layout">
        <SessionPanel
          groups={groups}
          total={total}
          activeId={activeId}
          query={query}
          onQueryChange={setQuery}
          onSelect={handleSelect}
          onCreate={handleCreate}
          onCollapse={collapse}
          onRename={handleRename}
          onRequestDelete={setPendingDeleteId}
        />

        {collapsed && <SessionDock onExpand={expand} onCreate={handleCreate} />}

        <div className="chat-panel">
          <div className="chat-heading">
            <div className="chat-heading-main">
              <span className="eyebrow">KNOWLEDGE CHAT</span>
              <h1>用团队知识回答问题</h1>
            </div>
            <span className="model-chip">检索 + 引用</span>
          </div>
          <MessageList messages={messages} onExpand={setFocusedId} />
          <Composer busy={busy} onSend={handleSend} onStop={stop} />
        </div>
      </section>

      {sessionsOpen && (
        <div className="session-overlay" role="presentation" onClick={() => setSessionsOpen(false)} />
      )}

      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}

      {pendingDelete && (
        <Modal
          confirm
          title="删除会话"
          onClose={() => setPendingDeleteId("")}
          footer={
            <div className="modal-footer-inner is-end">
              <button type="button" className="confirm-cancel" onClick={() => setPendingDeleteId("")}>
                取消
              </button>
              <button type="button" className="confirm-delete" onClick={handleConfirmDelete}>
                删除
              </button>
            </div>
          }
        >
          <p className="confirm-text">
            <b>{pendingDelete.title}</b> 将被删除。
          </p>
          <p className="confirm-hint">会话保存在本机，删除后无法恢复。</p>
        </Modal>
      )}

      {focused && (
        <FocusView message={focused.message} question={focused.question} onClose={() => setFocusedId(null)} />
      )}
    </main>
  );
}
