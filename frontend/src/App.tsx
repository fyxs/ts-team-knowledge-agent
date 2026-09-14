import { useState } from "react";
import { Composer } from "./components/Composer";
import { MessageList } from "./components/MessageList";
import { SettingsPanel } from "./components/SettingsPanel";
import { useAgentChat } from "./hooks/useAgentChat";
import { useTheme } from "./hooks/useTheme";

export default function App() {
  const { messages, busy, send, stop } = useAgentChat();
  const { theme, toggle } = useTheme();
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <main className="app-shell">
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
          <button type="button" className="theme-toggle" onClick={toggle} aria-label="切换主题">
            {theme === "dark" ? "浅色" : "深色"}
          </button>
          <button type="button" className="settings-button" onClick={() => setSettingsOpen(true)}>
            设置
          </button>
        </div>
      </header>

      <section className="chat-layout">
        <div className="chat-panel">
          <div className="chat-heading">
            <div>
              <span className="eyebrow">KNOWLEDGE CHAT</span>
              <h1>用团队知识回答问题</h1>
            </div>
            <span className="model-chip">检索 + 引用</span>
          </div>
          <MessageList messages={messages} />
          <Composer busy={busy} onSend={send} onStop={stop} />
        </div>
      </section>

      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}
    </main>
  );
}
