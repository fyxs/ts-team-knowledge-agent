import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchKnowledgeDocument, type AnswerSource, type KnowledgeDocument } from "../api/agent";
import { MarkdownView } from "./MarkdownView";

/** 一次读取的行数：足够覆盖一段上下文，又不至于把整篇文档灌进浏览器。 */
const WINDOW_LINES = 300;
/** 命中行上方预留的行数：落地时命中处不该贴着顶边。 */
const PRE_ROLL_LINES = 15;

/** 从命中片段里挑定位锚点：优先长片段，最多取三个候选依次尝试。 */
export function highlightCandidates(snippet: string): string[] {
  const runs = snippet.match(/[\u4e00-\u9fff]{2,}|[A-Za-z0-9_.\-/]{4,}/g) ?? [];
  return Array.from(new Set(runs.sort((left, right) => right.length - left.length))).slice(0, 3);
}

/** 在已渲染的正文里把命中文本包出来；找不到返回 null，调用方按「未定位」处理。 */
export function markNeedle(root: HTMLElement, needle: string): HTMLElement | null {
  if (!needle) return null;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    texts.push(node as Text);
  }
  for (const node of texts) {
    const index = node.data.indexOf(needle);
    if (index < 0) continue;
    const range = document.createRange();
    range.setStart(node, index);
    range.setEnd(node, index + needle.length);
    const mark = document.createElement("mark");
    // 用数据属性而不是类名标记「程序加的 mark」：正文自己也写 <mark>，
    // 清理时只能撤掉我们加的那一层，样式则统一走 .markdown-body mark。
    mark.dataset.sourceMark = "1";
    try {
      range.surroundContents(mark);
    } catch {
      continue;
    }
    return mark;
  }
  return null;
}

function clearMarks(root: HTMLElement) {
  root.querySelectorAll("mark[data-source-mark]").forEach((mark) => {
    const parent = mark.parentNode;
    if (!parent) return;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
    parent.normalize();
  });
}

type Props = {
  source: AnswerSource;
  onClose: () => void;
};

/**
 * 来源阅读：整屏放被引用的那篇文档，落在命中行并高亮。
 *
 * 结构照设计稿的集中阅读复用：.focus-view 外壳 + 单行头部（返回 / 来源 / 文档名，
 * 右侧一个命中胶囊）+ .messages 滚动区 + .source-doc 卡片（元信息行 + 正文）。
 * 只做三件事 —— 取正文、标命中、读得下去。入口只有一个「返回答案」；
 * 与集中阅读各退一层，靠 App 显式让路而不是事件阶段（见 FocusView 的 escDisabled）。
 */
export function SourceReader({ source, onClose }: Props) {
  const [doc, setDoc] = useState<KnowledgeDocument | null>(null);
  const [activeHit, setActiveHit] = useState(0);
  const [jumpToken, setJumpToken] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const hits = useMemo(() => source.hits ?? [], [source.hits]);
  const firstLine = hits[0]?.line ?? null;

  const loadWindow = useCallback(
    async (line: number | null, hitIndex: number) => {
      const offset = line === null ? 0 : Math.max(0, line - 1 - PRE_ROLL_LINES);
      setLoading(true);
      setError(null);
      setActiveHit(hitIndex);
      try {
        setDoc(await fetchKnowledgeDocument(source.path, offset, WINDOW_LINES));
        setJumpToken((token) => token + 1);
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : String(failure));
        setDoc(null);
      } finally {
        setLoading(false);
      }
    },
    [source.path],
  );

  useEffect(() => {
    void loadWindow(firstLine, 0);
  }, [firstLine, loadWindow]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    bodyRef.current?.focus({ preventScroll: true });
  }, []);

  // 标命中：正文一换就重标（追加读取后标记不会丢）。
  useEffect(() => {
    const container = bodyRef.current;
    if (!container || !doc) return;
    clearMarks(container);
    const snippet = hits[activeHit]?.snippet;
    if (!snippet) return;
    for (const candidate of highlightCandidates(snippet)) {
      if (markNeedle(container, candidate)) return;
    }
  }, [doc, activeHit, hits]);

  // 滚动只跟着「主动跳转」走：依赖里刻意不放 doc —— 追加读取时不该把读者拽回命中行。
  useEffect(() => {
    const container = bodyRef.current;
    if (!container || !doc) return;
    const mark = container.querySelector<HTMLElement>("mark[data-source-mark]");
    const card = container.querySelector<HTMLElement>(".source-doc");
    const target = mark ?? card;
    if (!(target instanceof HTMLElement)) return;
    // 用滚动容器自身的视口换算落点：offsetTop 的参照是最近的定位祖先（这里是
    // position:fixed 的 .source-view），直接拿它当 scrollTop 会多滚一个头部的高度，
    // 结果命中处被推到可视区上沿之外——「落在那一段」就落空了。
    const offsetInContent = (element: HTMLElement) =>
      element.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
    // 卡片自己的元信息行（完整路径、命中跳转）也在内容里：命中靠近文档开头时不能把它顶出去，
    // 否则「落在哪一段」看得到，「看的是哪篇、还能跳到哪几处」反而滚没了。
    const ceiling = card instanceof HTMLElement ? offsetInContent(card) : 0;
    const desired = offsetInContent(target) - 24;
    container.scrollTop = Math.max(0, Math.min(desired, Math.max(ceiling, 0)));
  }, [jumpToken]);

  const jumpTo = (index: number) => {
    const hit = hits[index];
    if (!hit) return;
    const loadedFrom = doc ? doc.offset + 1 : 0;
    const loadedTo = doc ? doc.offset + doc.returned_lines : 0;
    if (!doc || hit.line < loadedFrom || hit.line > loadedTo) {
      void loadWindow(hit.line, index);
      return;
    }
    setActiveHit(index);
    setJumpToken((token) => token + 1);
  };

  const loadMore = async () => {
    if (!doc) return;
    setLoading(true);
    setError(null);
    try {
      const next = await fetchKnowledgeDocument(source.path, doc.offset + doc.returned_lines, WINDOW_LINES);
      setDoc({
        ...next,
        offset: doc.offset,
        content: `${doc.content}\n${next.content}`,
        returned_lines: doc.returned_lines + next.returned_lines,
      });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setLoading(false);
    }
  };

  const loadedFrom = doc ? doc.offset + 1 : 0;
  const loadedTo = doc ? doc.offset + doc.returned_lines : 0;
  // 头部胶囊只说「命中了什么、第一处在哪」：命中数写在行上，位置可核对。
  const hitChip = hits.length === 0 ? "已引用" : `命中 ${hits.length} 处 · 第 ${hits[0].line} 行`;

  return (
    <div className="focus-view source-view" role="dialog" aria-modal="true" aria-label="来源文档">
      <header className="focus-head">
        <div className="focus-head-main">
          <button type="button" className="source-back" onClick={onClose}>
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M14.5 6 8.5 12l6 6" />
            </svg>
            返回答案
          </button>
          <span className="eyebrow">来源</span>
          <h1 title={doc?.title || source.title}>{doc?.title || source.title}</h1>
        </div>
        <div className="focus-head-side">
          <span className="source-hit-chip">{hitChip}</span>
        </div>
      </header>

      <div className="messages" ref={bodyRef} tabIndex={-1}>
        <div className="focus-doc">
          <article className="message source-doc">
            <div className="source-doc-meta">
              <span className="source-path" title={source.path}>
                {source.path}
              </span>
              <span aria-hidden="true">·</span>
              <span className="source-doc-kind">md{doc ? ` · 共 ${doc.total_lines} 行` : ""}</span>
              {/* 命中不止一处时才给跳转：一处的情况「返回答案」已经把人放在那里了。 */}
              {hits.length > 1 && (
                <div className="source-hits">
                  {hits.map((hit, index) => (
                    <button
                      key={`${hit.line}-${index}`}
                      type="button"
                      className={`source-hit${index === activeHit ? " is-active" : ""}`}
                      aria-pressed={index === activeHit}
                      onClick={() => jumpTo(index)}
                    >
                      第 {hit.line} 行
                    </button>
                  ))}
                </div>
              )}
            </div>
            {loading && !doc && <p className="source-status">正在读取文档…</p>}
            {error && <p className="source-status source-status-error">读取失败：{error}</p>}
            {doc && <MarkdownView content={doc.content} basePath={doc.path} />}
            {doc && doc.truncated && (
              <div className="source-foot">
                <span className="source-progress">
                  已读第 {loadedFrom}–{loadedTo} 行 / 共 {doc.total_lines} 行
                </span>
                <button type="button" className="source-more" onClick={() => void loadMore()} disabled={loading}>
                  {loading ? "读取中…" : "继续读取下方"}
                </button>
              </div>
            )}
            {doc && !doc.truncated && (
              <p className="source-progress source-progress-end">已读到文档末尾 · 共 {doc.total_lines} 行</p>
            )}
          </article>
        </div>
      </div>
    </div>
  );
}
