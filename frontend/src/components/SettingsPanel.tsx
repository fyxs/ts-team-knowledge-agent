import { useEffect, useState } from "react";
import { fetchModelConfig, saveModelConfig, type ModelConfig } from "../api/agent";

const FIELDS = [
  { key: "provider", label: "供应商", hint: "openai / anthropic 或自定义名称" },
  { key: "model", label: "模型名称", hint: "例如 deepseek-v4-flash" },
  { key: "base_url", label: "请求地址", hint: "缺省会自动补 /v1" },
] as const;

export function SettingsPanel() {
  const [config, setConfig] = useState<ModelConfig | null>(null);
  const [draft, setDraft] = useState<ModelConfig | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetchModelConfig()
      .then((loaded) => {
        setConfig(loaded);
        setDraft(loaded);
      })
      .catch((error: Error) => setStatus(`读取配置失败：${error.message}`));
  }, []);

  if (!draft) {
    return <p className="settings-note">{status || "加载中…"}</p>;
  }

  const dirty =
    config !== null &&
    (draft.provider !== config.provider ||
      draft.model !== config.model ||
      draft.base_url !== config.base_url ||
      draft.max_tokens !== config.max_tokens ||
      draft.max_steps !== config.max_steps);

  const save = async () => {
    setStatus("保存中…");
    try {
      const saved = await saveModelConfig({
        provider: draft.provider,
        model: draft.model,
        base_url: draft.base_url,
        max_tokens: Number(draft.max_tokens) || 4096,
        max_steps: Number(draft.max_steps) || 8,
      });
      setConfig(saved);
      setDraft(saved);
      setStatus("已保存，下一轮问答生效");
    } catch (error) {
      setStatus(`保存失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  return (
    <div className="settings-panel">
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
      <button type="button" className="save-button" onClick={save} disabled={!dirty}>保存配置</button>
      <div className="settings-note">
        <div>API Key：{draft.api_key}</div>
        <div>密钥不在此处修改，请用 <code>ts-team-kb config set-key</code>。</div>
        {status && <div className="settings-status">{status}</div>}
      </div>
    </div>
  );
}
