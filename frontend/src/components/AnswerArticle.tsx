import type { ReactNode } from "react";
import type { AnswerSource } from "../api/agent";
import type { ChatMessage } from "../hooks/useAgentChat";
import { MarkdownView } from "./MarkdownView";

type AnswerMessage = Extract<ChatMessage, { kind: "answer" }>;

type Props = {
  message: AnswerMessage;
  /** 答案块右上的操作。集中阅读视图内不传——已经在里面了，入口不该再出现。 */
  action?: ReactNode;
  /** 打开某条来源的阅读视图。不传时引用只作为文本展示。 */
  onOpenSource?: (source: AnswerSource) => void;
};

/** 行内只显示文档名，完整路径放 title 提示里：实测路径中位 64 字符，塞进一行会把命中信息挤掉。 */
function sourceLabel(source: AnswerSource, path: string): string {
  if (source.title.trim()) return source.title;
  const segments = path.split("/");
  return (segments[segments.length - 1] || path).replace(/\.md$/i, "");
}

/** 命中数 + 首处行号。没有检索词可定位时只说明「已引用」，不编造命中。 */
function hitSummary(source: AnswerSource): string {
  const first = source.hits[0];
  if (!first) return "已引用";
  return `命中 ${source.hits.length} 处 · 第 ${first.line} 行`;
}

/** 一条答案的完整呈现：标签 + 未检索提示 + 正文 + 来源。列表与集中阅读共用同一套。 */
export function AnswerArticle({ message, action, onOpenSource }: Props) {
  const byPath = new Map(message.sources.map((source) => [source.path, source]));

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
            {message.citations.map((citation) => {
              const source = byPath.get(citation);
              // 旧会话只存了路径字符串：退回纯文本，不给一个点不开的可点态。
              if (!source) {
                return (
                  <li key={citation}>
                    <span className="citation-static" title={citation}>
                      {citation}
                    </span>
                  </li>
                );
              }
              const body = (
                <>
                  <span className="citation-name">{sourceLabel(source, citation)}</span>
                  <span className="citation-meta">{hitSummary(source)}</span>
                  {onOpenSource && (
                    <span className="citation-arrow" aria-hidden="true">
                      →
                    </span>
                  )}
                </>
              );
              return (
                <li key={citation}>
                  {onOpenSource ? (
                    <button
                      type="button"
                      className="citation-row"
                      title={citation}
                      onClick={() => onOpenSource(source)}
                    >
                      {body}
                    </button>
                  ) : (
                    <span className="citation-row is-static" title={citation}>
                      {body}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </article>
  );
}
