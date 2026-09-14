import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Role = "user" | "assistant" | "tool" | "error";

type Message = {
  id: number;
  role: Role;
  content: string;
  citations?: string[];
};

type ModelConfig = {
  provider: string;
  model: string;
  base_url: string;
  max_tokens: number;
  max_steps: number;
  api_key: string;
};

const welcome: Message = {
  id: 1,
  role: "assistant",
  content:
    "你好，我是 TS 团队知识 Agent。你可以让我搜索、分析、总结或对比团队知识。回答会优先基于知识库，并标注来源。",
};

const emptyConfig: ModelConfig = {
  provider: "",
  model: "",
  base_url: "",
  max_tokens: 4096,
  max_steps: 8,
  api_key: "not configured",
};

function App() {
  const [messages, setMessages] = useState<Message[]>([welcome]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [config, setConfig] = useState<ModelConfig>(emptyConfig);
  const [savedHint, setSavedHint] = useState("");
  const nextId = useRef(2);
  const abortRef = useRef<AbortController | null>(null);

  const append = useCallback((message: Omit<Message, "id">) => {
    setMessages((current) => [...current, { ...message, id: nextId.current++ }]);
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/config");
      if (!response.ok) return;
      const payload = (await response.json()) as ModelConfig;
      setConfig(payload);
    } catch {
      /* 配置接口不可用时保持默认值 */
    }
  }, []);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const saveConfig = useCallback(async () => {
    setSavedHint("");
    try {
      const response = await fetch("/api/v1/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: config.provider,
          model: config.model,
          base_url: config.base_url,
          max_tokens: config.max_tokens,
          max_steps: config.max_steps,
        }),
      });
      if (!response.ok) {
        setSavedHint("保存失败");
        return;
      }
      const payload = (await response.json()) as ModelConfig;
      setConfig(payload);
      setSavedHint("已保存");
    } catch {
      setSavedHint("保存失败");
    }
  }, [config]);

  const handleEvent = useCallback(
    (event: Record<string, unknown>) => {
      const type = String(event.type ?? "");
      if (type === "start") {
        append({ role: "tool", content: "开始检索知识库…" });
      } else if (type === "tool_call") {
        const args = event.arguments as Record<string, unknown> | undefined;
        const detail = args ? JSON.stringify(args) : "";
        append({ role: "tool", content: `调用 ${event.name} ${detail}` });
      } else if (type === "tool_result") {
        const paths = (event.paths as string[]) ?? [];
        append({ role: "tool", content: `${event.name} 返回 ${paths.length} 条命中` });
      } else if (type === "answer") {
        append({
          role: "assistant",
          content: String(event.content ?? ""),
          citations: (event.citations as string[]) ?? [],
        });
      } else if (type === "error") {
        append({ role: "error", content: `出错了：${event.error}` });
      }
    },
    [append],
  );

  const sendMessage = useCallback(async () => {
    const question = draft.trim();
    if (!question || busy) return;
    setDraft("");
    append({ role: "user", content: question });
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await fetch("/api/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        append({ role: "error", content: `接口返回 ${response.status}` });
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((item) => item.startsWith("data: "));
          if (!line) continue;
          const data = line.slice(6);
          if (data === "[DONE]") continue;
          try {
            handleEvent(JSON.parse(data) as Record<string, unknown>);
          } catch {
            /* 忽略无法解析的事件 */
          }
        }
      }
    } catch (error) {
      if ((error as Error).name !== "AbortError") {
        append({ role: "error", content: `请求失败：${(error as Error).message}` });
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }, [append, busy, draft, handleEvent]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setBusy(false);
  }, []);

  const modelChip = useMemo(() => config.model || "未配置模型", [config.model]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">TS</span>
          <div>
            <strong>TS 团队知识 Agent</strong>
            <span>知识库检索 · 引用回答 · 本地优先</span>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="connection-status"><i />在线</span>
          <button className="settings-button" type="button" onClick={() => { setSettingsOpen((open) => !open); void loadConfig(); }}>
            {settingsOpen ? "收起设置" : "设置"}
          </button>
        </div>
      </header>

      <section className="chat-layout">
        <div className="chat-panel">
          <div className="chat-heading">
            <div>
              <span className="eyebrow">AGENT CHAT</span>
              <h1>向团队知识提问</h1>
            </div>
            <span className="model-chip">{modelChip}</span>
          </div>

          <div className="messages" data-testid="messages">
            {messages.map((message) => (
              <article className={`message message-${message.role}`} key={message.id}>
                <div className="message-label">
                  {message.role === "user" ? "你" : message.role === "assistant" ? "AGENT" : message.role === "tool" ? "工具" : "错误"}
                </div>
                <div className="message-body">
                  {message.content.split("\n").map((line, index) => (
                    <p key={index}>{line}</p>
                  ))}
                </div>
                {message.citations && message.citations.length > 0 && (
                  <div className="citation">来源：{message.citations.join(" · ")}</div>
                )}
              </article>
            ))}
            {busy && <div className="thinking">Agent 正在检索与整理…</div>}
          </div>

          <div className="composer">
            <textarea
              value={draft}
              placeholder="例如：团队移动端组件库的架构是怎样的？"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
            />
            <div className="composer-footer">
              <span>Enter 发送 · Shift+Enter 换行</span>
              {busy ? (
                <button type="button" onClick={stop}>停止</button>
              ) : (
                <button type="button" onClick={() => void sendMessage()} disabled={!draft.trim()}>发送</button>
              )}
            </div>
          </div>
        </div>

        {settingsOpen && (
          <aside className="settings-panel">
            <div className="panel-title">
              <span className="eyebrow">RUNTIME SETTINGS</span>
              <h2>运行设置</h2>
            </div>
            <label>
              供应商
              <input value={config.provider} onChange={(event) => setConfig({ ...config, provider: event.target.value })} />
            </label>
            <label>
              模型名称
              <input value={config.model} onChange={(event) => setConfig({ ...config, model: event.target.value })} />
            </label>
            <label>
              请求地址
              <input value={config.base_url} onChange={(event) => setConfig({ ...config, base_url: event.target.value })} />
            </label>
            <label>
              最大步数
              <input type="number" min={1} max={30} value={config.max_steps} onChange={(event) => setConfig({ ...config, max_steps: Number(event.target.value) || 1 })} />
            </label>
            <label>
              API Key
              <input value={config.api_key} readOnly />
            </label>
            <button className="settings-button" type="button" onClick={() => void saveConfig()} style={{ marginTop: 18 }}>
              保存设置
            </button>
            {savedHint && <div className="settings-note">{savedHint}</div>}
            <div className="settings-note">
              密钥只在本机保存，不通过页面回显，也不进入任何仓库。修改密钥请在命令行执行 ts-team-kb config set-key。
            </div>
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
