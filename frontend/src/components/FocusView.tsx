import { useEffect } from "react";
import type { ChatMessage } from "../hooks/useAgentChat";
import { AnswerArticle } from "./AnswerArticle";

type AnswerMessage = Extract<ChatMessage, { kind: "answer" }>;

type Props = {
  message: AnswerMessage;
  /** 头部显示这个问题——比「集中阅读」四个字更能说明正在看的是哪一段。 */
  question: string;
  onClose: () => void;
};

/** 集中阅读：整屏只呈现一条答案，去掉会话列表、顶栏与输入区，把高度让给正文。 */
export function FocusView({ message, question, onClose }: Props) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

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
          <AnswerArticle message={message} />
        </div>
      </div>
    </div>
  );
}
