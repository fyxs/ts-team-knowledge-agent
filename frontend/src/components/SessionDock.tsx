type Props = {
  onExpand: () => void;
  onCreate: () => void;
};

/** 会话列收起后浮出的按钮组：打开历史面板 + 快捷新建对话。 */
export function SessionDock({ onExpand, onCreate }: Props) {
  return (
    <div className="session-dock">
      <button
        type="button"
        className="dock-button"
        onClick={onExpand}
        title="打开历史面板"
        aria-label="打开历史面板"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M9.6 4v16" />
        </svg>
      </button>
      <button
        type="button"
        className="dock-button"
        onClick={onCreate}
        title="新建对话"
        aria-label="新建对话"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
          <path d="M12 5v14M5 12h14" />
        </svg>
      </button>
    </div>
  );
}
