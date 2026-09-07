import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Metric = { label: string; value: string; detail: string };

const metrics: Metric[] = [
  { label: "知识源", value: "未配置", detail: "等待 CLI 初始化" },
  { label: "处理队列", value: "0", detail: "暂无待处理任务" },
  { label: "Git 同步", value: "未运行", detail: "每小时批次同步" },
];

function App() {
  return (
    <main className="app-shell">
      <header className="hero">
        <div className="brand-mark">TS</div>
        <div>
          <p className="eyebrow">TS KNOWLEDGE AGENT / V0.1</p>
          <h1>把日常材料，变成团队可用的知识。</h1>
          <p className="lede">本地优先 · Agent 驱动 · Git 共享 · 源文件只读</p>
        </div>
        <span className="status-pill"><i /> 骨架运行中</span>
      </header>

      <section className="metrics" aria-label="系统概览">
        {metrics.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <span className="metric-label">{metric.label}</span>
            <strong>{metric.value}</strong>
            <span className="metric-detail">{metric.detail}</span>
          </article>
        ))}
      </section>

      <section className="workspace-grid">
        <article className="panel primary-panel">
          <div className="panel-heading">
            <div><span className="kicker">KNOWLEDGE WORKSPACE</span><h2>本地知识处理</h2></div>
            <span className="panel-index">01</span>
          </div>
          <p>成员按自己的习惯放置材料，Agent 负责扫描、转换、提炼和沉淀；不移动、不覆盖、不删除源文件。</p>
          <div className="flow">
            {["本地源目录", "MinerU", "知识沉淀", "Git 仓"].map((item, index) => <React.Fragment key={item}><span>{item}</span>{index < 3 && <b>→</b>}</React.Fragment>)}
          </div>
          <button className="primary-action" type="button" disabled>初始化本地空间 <span>即将支持</span></button>
        </article>

        <article className="panel search-panel">
          <div className="panel-heading"><div><span className="kicker">SEARCH</span><h2>搜索团队知识</h2></div><span className="panel-index">02</span></div>
          <p>搜索接口将在第一期接入 SQLite FTS5，结果将携带来源和知识状态。</p>
          <label className="search-box"><span>⌕</span><input disabled placeholder="搜索文件、知识或项目" /><kbd>⌘ K</kbd></label>
          <div className="empty-state"><span className="empty-icon">⌁</span><span>知识索引尚未初始化</span></div>
        </article>
      </section>

      <footer><span>AG-UI：协议边界已确定，默认 SSE</span><span>Harness：沿用当前工作模型</span><span>ts-team-knowledge-base：固定远程仓</span></footer>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
