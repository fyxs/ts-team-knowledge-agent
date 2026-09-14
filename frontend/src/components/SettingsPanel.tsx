import { useCallback, useEffect, useRef, useState } from "react";
import { Modal } from "./Modal";
import {
  fetchModelConfig,
  fetchRunStatus,
  pullKnowledgeRepository,
  pushKnowledgeRepository,
  saveModelConfig,
  triggerRun,
  type ModelConfig,
  type RunStatus,
} from "../api/agent";

const FIELDS = [
  { key: "provider", label: "供应商", hint: "openai / anthropic 或自定义名称" },
  { key: "model", label: "模型名称", hint: "例如 deepseek-v4-flash" },
  { key: "base_url", label: "请求地址", hint: "缺省会自动补 /v1" },
] as const;

function describeRun(status: RunStatus): string {
  if (status.running) return "正在扫描与转换…";
  const last = status.last;
  if (last?.status === "error") return `上轮出错：${last.error ?? "未知错误"}`;
  if (last?.status === "finished") {
    return `上轮：扫描 ${last.scanned ?? 0}，转换 ${last.converted ?? 0}，跳过 ${last.skipped ?? 0}，失败 ${last.failed ?? 0}，同步 ${last.sync_status ?? "-"}`;
  }
  const report = status.report as { converted?: number; sync_status?: string } | null;
  if (report) return `最近一轮记录：转换 ${report.converted ?? 0}，同步 ${report.sync_status ?? "-"}`;
  return "尚无运行记录";
}

export function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [config, setConfig] = useState<ModelConfig | null>(null);
  const [draft, setDraft] = useState<ModelConfig | null>(null);
  const [configStatus, setConfigStatus] = useState("");
  const [scanStatus, setScanStatus] = useState("");
  const [syncStatus, setSyncStatus] = useState("");
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const [busyAction, setBusyAction] = useState("");
  const pollRef = useRef<number | null>(null);

  const refreshRunStatus = useCallback(async () => {
    try {
      setRunStatus(await fetchRunStatus());
    } catch (error) {
      setScanStatus(`读取运行状态失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }, []);

  useEffect(() => {
    fetchModelConfig()
      .then((loaded) => {
        setConfig(loaded);
        setDraft(loaded);
      })
      .catch((error: Error) => setConfigStatus(`读取配置失败：${error.message}`));
    void refreshRunStatus();
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, [refreshRunStatus]);

  const startScan = async () => {
    setBusyAction("scan");
    setScanStatus("已触发扫描，正在后台执行…");
    try {
      const result = await triggerRun({ sync: true });
      if (result.status === "busy") {
        setScanStatus("已有扫描在运行，未重复触发");
      }
      await refreshRunStatus();
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
      pollRef.current = window.setInterval(async () => {
        const current = await fetchRunStatus().catch(() => null);
        if (current) setRunStatus(current);
        if (!current || !current.running) {
          if (pollRef.current !== null) window.clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }, 5000);
    } catch (error) {
      setScanStatus(`触发扫描失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusyAction("");
    }
  };

  const syncAction = async (kind: "pull" | "push") => {
    setBusyAction(kind);
    setSyncStatus(kind === "pull" ? "正在拉取共享知识仓…" : "正在推送共享知识仓…");
    try {
      const result = kind === "pull" ? await pullKnowledgeRepository() : await pushKnowledgeRepository();
      const detail = result.message ? `（${result.message}）` : "";
      const commit = result.commit ? ` commit=${result.commit.slice(0, 8)}` : "";
      setSyncStatus(`${kind === "pull" ? "拉取" : "推送"}结果：${result.status}${detail}${commit}`);
    } catch (error) {
      setSyncStatus(`${kind === "pull" ? "拉取" : "推送"}失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusyAction("");
    }
  };

  if (!draft) {
    return (
      <Modal title="运行配置" onClose={onClose}>
        <p className="settings-note">{configStatus || "加载中…"}</p>
      </Modal>
    );
  }

  const dirty =
    config !== null &&
    (draft.provider !== config.provider ||
      draft.model !== config.model ||
      draft.base_url !== config.base_url ||
      draft.max_tokens !== config.max_tokens ||
      draft.max_steps !== config.max_steps ||
      draft.scan_interval_minutes !== config.scan_interval_minutes);

  const save = async () => {
    setConfigStatus("保存中…");
    try {
      const saved = await saveModelConfig({
        provider: draft.provider,
        model: draft.model,
        base_url: draft.base_url,
        max_tokens: Number(draft.max_tokens) || 4096,
        max_steps: Number(draft.max_steps) || 8,
        scan_interval_minutes: Math.max(5, Number(draft.scan_interval_minutes) || 60),
      });
      setConfig(saved);
      setDraft(saved);
      setConfigStatus("已保存");
    } catch (error) {
      setConfigStatus(`保存失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  return (
    <Modal
      title="运行配置"
      onClose={onClose}
      footer={
        <div className="modal-footer-inner">
          {configStatus && <span className="settings-status">{configStatus}</span>}
          <button type="button" className="save-button" onClick={save} disabled={!dirty}>
            保存配置
          </button>
        </div>
      }
    >
      <div className="settings-panel">
      <section className="settings-section">
        <h3 className="settings-section-title">模型</h3>
        {FIELDS.map((field) => (
          <label key={field.key}>
            {field.label}
            <input
              value={draft[field.key]}
              placeholder={field.hint}
              onChange={(event) => setDraft({ ...draft, [field.key]: event.target.value })}
            />
            <span className="field-hint">{field.hint}</span>
          </label>
        ))}
        <label>
          最大步数
          <input
            type="number"
            min={1}
            max={20}
            value={draft.max_steps}
            onChange={(event) => setDraft({ ...draft, max_steps: Number(event.target.value) || 1 })}
          />
          <span className="field-hint">Agent 一轮最多调用多少次工具</span>
        </label>
        <label>
          最大输出 Token
          <input
            type="number"
            min={256}
            step={256}
            value={draft.max_tokens}
            onChange={(event) => setDraft({ ...draft, max_tokens: Number(event.target.value) || 4096 })}
          />
        </label>
      </section>

      <section className="settings-section">
        <h3 className="settings-section-title">扫描</h3>
        <label>
          扫描间隔（分钟）
          <input
            type="number"
            min={5}
            max={1440}
            value={draft.scan_interval_minutes}
            onChange={(event) => setDraft({ ...draft, scan_interval_minutes: Number(event.target.value) || 5 })}
          />
          <span className="field-hint">不低于 5 分钟；计划任务按此间隔判断本轮是否执行，默认 60 分钟</span>
        </label>
        <div className="settings-actions">
          <button type="button" onClick={startScan} disabled={busyAction === "scan"}>
            立即扫描
          </button>
          <button type="button" onClick={() => void refreshRunStatus()}>刷新状态</button>
        </div>
        <div className="settings-status">
          {scanStatus && <div>{scanStatus}</div>}
          <div>{runStatus ? describeRun(runStatus) : "正在读取运行状态…"}</div>
        </div>
      </section>

      <section className="settings-section">
        <h3 className="settings-section-title">共享知识仓</h3>
        <div className="settings-actions">
          <button type="button" onClick={() => void syncAction("pull")} disabled={busyAction === "pull"}>
            拉取
          </button>
          <button type="button" onClick={() => void syncAction("push")} disabled={busyAction === "push"}>
            推送
          </button>
        </div>
        <div className="settings-status">{syncStatus || "尚未执行同步操作"}</div>
        <span className="field-hint">拉取只在工作区干净时执行；推送会先提交本轮产生的知识再推送。</span>
      </section>

      <section className="settings-section">
        <h3 className="settings-section-title">密钥</h3>
        <div className="settings-note">
          <div>API Key：{draft.api_key}</div>
          <div>密钥不在此处修改，请用 <code>ts-team-kb config set-key</code>。</div>
        </div>
      </section>
      </div>
    </Modal>
  );
}
