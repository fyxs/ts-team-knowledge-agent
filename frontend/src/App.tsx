import { useCallback, useState } from "react";
import { Composer } from "./components/Composer";
import { MessageList } from "./components/MessageList";
import { SessionDock } from "./components/SessionDock";
import { SessionPanel } from "./components/SessionPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { useAgentChat } from "./hooks/useAgentChat";
import { useSessions } from "./hooks/useSessions";
import { useTheme } from "./hooks/useTheme";

export default function App() {
  const { groups, total, activeId, query, setQuery, collapsed, createSession, selectSession, touchSession, collapse, expand } =
    useSessions();
  const { messages, busy, send, stop } = useAgentChat(activeId);
  const { theme, toggle } = useTheme();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);

  const handleSend = useCallback(
    (question: string) => {
      touchSession(activeId, question);
      void send(question);
    },
    [activeId, send, touchSession],
  );

  const handleCreate = useCallback(() => {
    createSession();
    setSessionsOpen(false);
  }, [createSession]);

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
        />

        {collapsed && <SessionDock onExpand={expand} onCreate={handleCreate} />}

        <div className="chat-panel">
          <div className="chat-heading">
            <div>
              <span className="eyebrow">KNOWLEDGE CHAT</span>
              <h1>用团队知识回答问题</h1>
            </div>
            <span className="model-chip">检索 + 引用</span>
          </div>
          <MessageList messages={messages} />
          <Composer busy={busy} onSend={handleSend} onStop={stop} />
        </div>
      </section>

      {sessionsOpen && (
        <div className="session-overlay" role="presentation" onClick={() => setSessionsOpen(false)} />
      )}

      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}
    </main>
  );
}
