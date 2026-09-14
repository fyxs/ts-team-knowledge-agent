import { StrictMode, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Role = "user" | "assistant" | "tool";
type Message = { id: number; role: Role; content: string; source?: string };

type Settings = {
  model: string;
  topK: number;
  requireCitations: boolean;
};

const initialMessages: Message[] = [
  {
    id: 1,
    role: "assistant",
    content:
      "你好，我是 TS 团队知识 Agent。你可以让我搜索、分析、总结或对比团队知识。回答会优先基于知识库，并标注来源。",
  },
];

const defaultSettings: Settings = {
  model: "待接入模型",
  topK: 8,
  requireCitations: true,
};

function MessageBubble({ message }: { message: Message }) {
  const className = `message message-${message.role}`;
  return (
    <article className={className}>
      <div className="message-label">
        {message.role === "user" ? "你" : message.role === "tool" ? "知识库工具" : "TS Agent"}
      </div>
      <div className="message-body">
        {message.content.split("\n").map((line, index) => (
          <p key={`${message.id}-${index}`}>{line || "\u00a0"}</p>
        ))}
      </div>
      {message.source && <div className="citation">来源：{message.source}</div>}
    </article>
  );
}

function App() {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState("");
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const canSend = useMemo(() => input.trim().length > 0 && !busy, [input, busy]);

  function sendMessage() {
    const content = input.trim();
    if (!content || busy) return;
    const userMessage: Message = { id: Date.now(), role: "user", content };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setBusy(true);

    window.setTimeout(() => {
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "tool",
          content: `已准备检索知识库（Top-K: ${settings.topK}）。模型接口接入后，这里将显示真实检索过程。`,
        },
        {
          id: Date.now() + 2,
          role: "assistant",
          content:
            "当前是 Web Chat UI 冒烟模式。下一步接入 Agent API 后，我会先搜索相关知识，再基于检索结果回答。",
          source: "知识库工具接入待完成",
        },
      ]);
      setBusy(false);
    }, 450);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">TS</div>
          <div>
            <strong>TS Knowledge Agent</strong>
            <span>轻量 Agent Web Chat</span>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="connection-status"><i /> Agent Runtime 待接入</span>
          <button className="settings-button" type="button" onClick={() => setSettingsOpen((open) => !open)}>
            设置
          </button>
        </div>
      </header>

      <section className="chat-layout">
        <div className="chat-panel">
          <div className="chat-heading">
            <div>
              <span className="eyebrow">KNOWLEDGE CONVERSATION</span>
              <h1>和团队知识对话</h1>
            </div>
            <span className="model-chip">{settings.model}</span>
          </div>

          <div className="messages" aria-live="polite">
            {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
            {busy && <div className="thinking">Agent 正在准备检索…</div>}
          </div>

          <div className="composer">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  sendMessage();
                }
              }}
              placeholder="搜索、分析或总结团队知识…"
              rows={2}
            />
            <div className="composer-footer">
              <span>Enter 发送 · Shift+Enter 换行</span>
              <button type="button" onClick={sendMessage} disabled={!canSend}>{busy ? "处理中…" : "发送"}</button>
            </div>
          </div>
        </div>

        {settingsOpen && (
          <aside className="settings-panel">
            <div className="panel-title"><span className="eyebrow">RUNTIME SETTINGS</span><h2>运行配置</h2></div>
            <label>模型<select value={settings.model} onChange={(event) => setSettings({ ...settings, model: event.target.value })}><option>待接入模型</option><option>Harness 工作模型</option></select></label>
            <label>检索 Top-K<input type="number" min={1} max={50} value={settings.topK} onChange={(event) => setSettings({ ...settings, topK: Number(event.target.value) || 1 })} /></label>
            <label className="check-row"><input type="checkbox" checked={settings.requireCitations} onChange={(event) => setSettings({ ...settings, requireCitations: event.target.checked })} /> 要求回答附来源</label>
            <div className="settings-note">一期配置页面只调整 Agent 运行参数，不提供管理员权限，也不管理知识库文件。</div>
          </aside>
        )}
      </section>
    </main>
  );
}

export default App;

const container = document.getElementById("root");

if (container) {
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
