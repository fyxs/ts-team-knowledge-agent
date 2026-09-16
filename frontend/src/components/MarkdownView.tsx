import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { knowledgeAssetUrl } from "../api/agent";

/**
 * 统一的 Markdown 渲染入口。
 * 只依赖 react-markdown + remark-gfm；如后续需要流式/数学/图表插件，
 * 只替换本组件即可，其它层不受影响。
 *
 * `basePath` 是当前文档在知识仓里的路径：给了它，文档内的相对图片才能解析成
 * `/api/v1/knowledge/asset` 请求。答案正文没有 basePath，其中的相对图片一律显示为不可用。
 */
type Props = {
  content: string;
  /** 当前正文所属文档的知识仓相对路径；答案正文不传。 */
  basePath?: string;
};

type ImageSource =
  | { kind: "asset"; url: string }
  | { kind: "external"; url: string }
  | { kind: "unavailable" };

const WINDOWS_DRIVE = /^[a-zA-Z]:[\\/]/;

/** 文档内的图片地址分流：能走知识仓路由的走路由，其余如实标出不可用，不猜测也不热链。 */
function classifyImage(raw: string, basePath?: string): ImageSource {
  const src = raw.trim();
  if (!src) return { kind: "unavailable" };
  if (/^https?:\/\//i.test(src)) return { kind: "external", url: src };
  // 本机绝对路径（作者自己机器上的 Typora 目录）与协议相对地址都取不到，不要拼成知识仓路径。
  if (WINDOWS_DRIVE.test(src) || src.startsWith("/") || src.startsWith("//")) {
    return { kind: "unavailable" };
  }
  if (!basePath) return { kind: "unavailable" };
  const directory = basePath.slice(0, basePath.lastIndexOf("/"));
  if (!directory) return { kind: "unavailable" };
  const prefix = `${directory}/`;
  const resolved = src.startsWith("./") ? src.slice(2) : src;
  const target = resolved
    .split("/")
    .reduce<string[]>((segments, segment) => {
      if (segment === "..") segments.pop();
      else if (segment !== ".") segments.push(segment);
      return segments;
    }, [])
    .join("/");
  if (!target || target.startsWith("..")) return { kind: "unavailable" };
  return { kind: "asset", url: knowledgeAssetUrl(prefix + target) };
}

function renderImage(raw: string, alt: string, basePath?: string) {
  const source = classifyImage(raw, basePath);
  if (source.kind === "asset") {
    return <img className="content-img" src={source.url} alt={alt} loading="lazy" />;
  }
  if (source.kind === "external") {
    return (
      <a className="image-external" href={source.url} target="_blank" rel="noreferrer" title={source.url}>
        {alt || "外部图片"}（站外地址，未随知识仓入库）
      </a>
    );
  }
  return (
    <span className="image-missing" title={raw}>
      图片不可用：原文档引用的是本机或站外地址
    </span>
  );
}

export function MarkdownView({ content, basePath }: Props) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
          img: ({ src, alt }) => renderImage(typeof src === "string" ? src : "", alt ?? "", basePath),
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
