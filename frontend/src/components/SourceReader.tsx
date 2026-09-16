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
    mark.className = "source-mark";
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
  root.querySelectorAll("mark.source-mark").forEach((mark) => {
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
    const mark = container.querySelector<HTMLElement>("mark.source-mark");
    const target = mark ?? container.firstElementChild;
    if (!(target instanceof HTMLElement)) return;
    container.scrollTop = Math.max(0, target.offsetTop - 24);
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

  return (
    <div className="source-view" role="dialog" aria-modal="true" aria-label="来源文档">
      <header className="source-head">
        <div className="source-head-top">
          <button type="button" className="source-back" onClick={onClose}>
            ← 返回答案
          </button>
          <span className="eyebrow">来源文档</span>
        </div>
        <h1>{doc?.title || source.title}</h1>
        <p className="source-path" title={source.path}>
          {source.path}
        </p>
        <div className="source-hits">
          {hits.length > 0 ? (
            <>
              <span className="source-hits-label">命中 {hits.length} 处</span>
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
            </>
          ) : (
            <span className="source-hits-label">已引用</span>
          )}
        </div>
      </header>
      <div className="source-body" ref={bodyRef} tabIndex={-1}>
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
      </div>
    </div>
  );
}
