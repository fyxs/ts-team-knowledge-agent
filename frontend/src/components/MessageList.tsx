import type { ChatMessage } from "../hooks/useAgentChat";
import { MarkdownView } from "./MarkdownView";
import { ProcessBlock } from "./ProcessBlock";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  if (messages.length === 0) {
    return (
      <div className="empty-state">
        <p>向团队知识库提问，例如：</p>
        <ul>
          <li>团队移动端组件库的架构是怎样的？</li>
          <li>前端编码规范里对环境变量有什么要求？</li>
        </ul>
      </div>
    );
  }

  return (
    <div className="messages">
      {messages.map((message) => {
        if (message.kind === "user") {
          return (
            <article className="message message-user" key={message.id}>
              <div className="message-label">我</div>
              <div className="message-body">{message.content}</div>
            </article>
          );
        }
        if (message.kind === "process") {
          return <ProcessBlock key={message.id} steps={message.steps} running={message.running} durationMs={message.durationMs} />;
        }
        if (message.kind === "answer") {
          return (
            <article className="message message-assistant" key={message.id}>
              <div className="message-label">知识 Agent</div>
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
        return (
          <article className="message message-error" key={message.id}>
            <div className="message-label">出错</div>
            <div className="message-body">{message.message}</div>
          </article>
        );
      })}
    </div>
  );
}
