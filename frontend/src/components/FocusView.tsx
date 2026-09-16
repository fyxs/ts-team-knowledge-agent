import { useEffect } from "react";
import type { AnswerSource } from "../api/agent";
import type { ChatMessage } from "../hooks/useAgentChat";
import { AnswerArticle } from "./AnswerArticle";

type AnswerMessage = Extract<ChatMessage, { kind: "answer" }>;

type Props = {
  message: AnswerMessage;
  /** 头部显示这个问题——比「集中阅读」四个字更能说明正在看的是哪一段。 */
  question: string;
  onClose: () => void;
  /** 打开某条引用来源的阅读视图。来源层压在集中阅读之上，Esc 逐层退。 */
  onOpenSource: (source: AnswerSource) => void;
  /** 来源阅读层打开时置真：这一层暂时不接 Esc，避免一次退两层。 */
  escDisabled?: boolean;
};

/** 集中阅读：整屏只呈现一条答案，去掉会话列表、顶栏与输入区，把高度让给正文。 */
export function FocusView({ message, question, onClose, onOpenSource, escDisabled = false }: Props) {
  useEffect(() => {
    if (escDisabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [escDisabled, onClose]);

  return (
    <div className="focus-view">
      <header className="focus-head">
        <div className="focus-head-main">
          <span className="eyebrow">集中阅读</span>
          <h1>{question}</h1>
        </div>
        <button type="button" className="focus-close" onClick={onClose} aria-label="退出集中阅读">
          ×
        </button>
      </header>
      <div className="messages">
        <div className="focus-doc">
          <AnswerArticle message={message} onOpenSource={onOpenSource} />
        </div>
      </div>
    </div>
  );
}
