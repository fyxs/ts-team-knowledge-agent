import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { fetchKnowledgeDocument, type AnswerSource, type KnowledgeDocument } from "../api/agent";
import { MarkdownView } from "./MarkdownView";

/** 一次读取的行数：足够覆盖一段上下文，又不至于把整篇文档灌进浏览器。 */
const WINDOW_LINES = 300;
/** 命中行上方预留的行数：落地时命中处不该贴着顶边。 */
const PRE_ROLL_LINES = 15;
/** 落点留白：命中处对到滚动区顶部时留这么高，文字才不贴边。 */
const LANDING_AIR = 24;

/** 跳转信号要的落点方式：新取的一段窗口 / 窗口内的某一处命中。 */
type JumpAlign = "window" | "hit";

/**
 * 「层」的落点：把命中处对到滚动区顶部下方留白处，不越过内容顶端。
 * 点命中按钮时用它——位移本身就是反馈，命中已在视野里也照样对齐。
 */
export function landingScrollTop(markTop: number): number {
  return Math.max(0, markTop - LANDING_AIR);
}

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
 * 结构照设计稿的集中阅读复用：.focus-view 外壳 + 单行头部（来源 / 文档名 / 右上角 ×）+
 * .messages 滚动区 + .source-doc 卡片（元信息行 + 正文）。头部与集中阅读完全同一套 ——
 * 退出都是右上角那个 ×，Esc 同义；它与集中阅读各退一层，靠 App 显式让路而不是事件阶段
 * （见 FocusView 的 escDisabled）。
 *
 * 命中信息与跳转同在卡片元信息行右端：处数是值，行号按钮是去处，不必在两处之间对照。
 */
export function SourceReader({ source, onClose }: Props) {
  const [doc, setDoc] = useState<KnowledgeDocument | null>(null);
  const [activeHit, setActiveHit] = useState(0);
  const [jump, setJump] = useState<{ token: number; align: JumpAlign }>({ token: 0, align: "window" });
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
        // 新取的一段窗口从头看：窗口本身就从命中行上方 15 行开始，
        // 顶部同时给出「这是哪篇文档」和「命中的那一段」。
        setJump((previous) => ({ token: previous.token + 1, align: "window" }));
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

  // 滚动只跟着跳转信号走：loadMore 不动 jump，追加读取就不会把读者拽回命中行。
  // 用 useLayoutEffect 而不是 useEffect：正文换掉后浏览器还停在旧 scrollTop 上，
  // 等绘制之后再纠正会先闪一帧错位的内容。
  useLayoutEffect(() => {
    const container = bodyRef.current;
    if (!container) return;
    if (jump.align === "window") {
      container.scrollTop = 0;
      return;
    }
    const mark = container.querySelector<HTMLElement>("mark[data-source-mark]");
    const card = container.querySelector<HTMLElement>(".source-doc");
    const target = mark ?? card;
    if (!(target instanceof HTMLElement)) return;
    // 用滚动容器自身的视口换算落点：offsetTop 的参照是最近的定位祖先（这里是
    // position:fixed 的 .source-view），直接拿它当 scrollTop 会多滚一个头部的高度，
    // 结果命中处被推到可视区上沿之外——「落在那一段」就落空了。
    const markTop =
      target.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
    container.scrollTop = landingScrollTop(markTop);
  }, [jump]);

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
    // 窗口内的命中：把命中处对到顶部留白处。即使它已在视野里也照样对齐——按了要有位移，
    // 落点固定在同一高度，读者一眼就知道跳到哪了。
    setJump((previous) => ({ token: previous.token + 1, align: "hit" }));
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
  // 命中信息与跳转同在元信息行右端：命中不止一处时行号由按钮给出，胶囊只报处数；
  // 只有一处时没有按钮，行号就得由胶囊说清。
  const hitChip =
    hits.length === 0
      ? "已引用"
      : hits.length === 1
        ? `命中 1 处 · 第 ${hits[0].line} 行`
        : `命中 ${hits.length} 处`;

  return (
    <div className="focus-view source-view" role="dialog" aria-modal="true" aria-label="来源文档">
      <header className="focus-head">
        <div className="focus-head-main">
          <span className="eyebrow">来源</span>
          <h1 title={doc?.title || source.title}>{doc?.title || source.title}</h1>
        </div>
        {/* 退出与集中阅读是同一套：右上角一个 ×，Esc 同义。去向唯一，不再放第二个出口。 */}
        <button type="button" className="focus-close" onClick={onClose} aria-label="退出来源阅读">
          ×
        </button>
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
              <span className="source-hit-chip">{hitChip}</span>
              {/* 命中不止一处时才给跳转：一处的情况进来就在那一行上，没有别处可跳。 */}
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
