import type { ReactNode } from "react";
import type { ChatMessage } from "../hooks/useAgentChat";
import { MarkdownView } from "./MarkdownView";

type AnswerMessage = Extract<ChatMessage, { kind: "answer" }>;

type Props = {
  message: AnswerMessage;
  /** 答案块右上的操作。集中阅读视图内不传——已经在里面了，入口不该再出现。 */
  action?: ReactNode;
};

/** 一条答案的完整呈现：标签 + 未检索提示 + 正文 + 来源。列表与集中阅读共用同一套。 */
export function AnswerArticle({ message, action }: Props) {
  return (
    <article className="message message-assistant">
      <div className="message-label">
        <span>知识 Agent</span>
        {action}
      </div>
      {!message.retrieved && (
        <p className="unretrieved-note">本次回答未检索知识库，请谨慎采纳。</p>
      )}
      <MarkdownView content={message.content} />
      {message.citations.length > 0 && (
        <div className="citation">
          <div className="citation-title">来源（{message.citations.length}）</div>
          <ul>
            {message.citations.map((citation) => (
              <li key={citation}>{citation}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
