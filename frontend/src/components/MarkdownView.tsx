import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * 统一的 Markdown 渲染入口。
 * 只依赖 react-markdown + remark-gfm；如后续需要流式/数学/图表插件，
 * 只替换本组件即可，其它层不受影响。
 */
export function MarkdownView({ content }: { content: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
          table: ({ node, ...props }) => (
            <div className="table-scroll">
              <table {...props} />
            </div>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
