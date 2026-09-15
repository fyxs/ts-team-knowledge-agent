import { useEffect, type ReactNode } from "react";

type Props = {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** 固定在底部的操作区；只放主操作与结果提示，不随内容滚动。 */
  footer?: ReactNode;
  /** 确认框变体：更窄、去分隔线。内容只有几行的二次确认用它。 */
  confirm?: boolean;
};

/** 通用弹窗容器：头部与底部固定，仅中间内容区滚动；Esc 与点击遮罩关闭。 */
export function Modal({ title, onClose, children, footer, confirm = false }: Props) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div
        className={confirm ? "modal-panel is-confirm" : "modal-panel"}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
