import { useState } from "react";

type Props = {
  busy: boolean;
  onSend: (question: string) => void;
  onStop: () => void;
};

export function Composer({ busy, onSend, onStop }: Props) {
  const [value, setValue] = useState("");
  const canSend = value.trim().length > 0 && !busy;

  const submit = () => {
    if (!canSend) return;
    onSend(value);
    setValue("");
  };

  return (
    <div className="composer">
      <textarea
        value={value}
        placeholder="问点团队知识相关的问题…（Enter 发送，Shift+Enter 换行）"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
      />
      <div className="composer-footer">
        <span>{busy ? "Agent 正在检索与作答…" : "回答会标注知识库来源"}</span>
        {busy ? (
          <button type="button" onClick={onStop}>停止</button>
        ) : (
          <button type="button" onClick={submit} disabled={!canSend}>发送</button>
        )}
      </div>
    </div>
  );
}
