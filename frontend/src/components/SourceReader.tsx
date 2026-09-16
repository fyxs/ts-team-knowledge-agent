import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { fetchKnowledgeDocument, type AnswerSource, type KnowledgeDocument } from "../api/agent";
import { MarkdownView } from "./MarkdownView";

/** 一次读取的行数：足够覆盖一段上下文，又不至于把整篇文档灌进浏览器。 */
const WINDOW_LINES = 300;
/** 命中行上方预留的行数：落地时命中处不该贴着顶边。 */
const PRE_ROLL_LINES = 15;
/** 落点留白：命中处对到滚动区顶部时留这么高，文字才不贴边。 */
const LANDING_AIR = 24;
/**
 * 一段话的边界：跨行内节点找命中时只在同一个块里把文本拼起来，不跨段落拼 ——
 * 跨段落拼会拼出正文里并不存在的句子。
 */
const BLOCK_SELECTOR = "p, li, td, th, dt, dd, h1, h2, h3, h4, h5, h6, blockquote, pre, figcaption";

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

/**
 * 命中行在已读窗口里的估算高度（0–h）。行号排在窗口里的比例位置乘滚动高度。
 *
 * 它只做两件事，都不要求准：给「同一段文本在一屏里出现多次」排序，以及在命中文本
 * 定位不到时给个比窗口顶部更近的兜底。渲染后的行高不等（表格、代码块都更占地方），
 * 所以估算不能被当成落点本身 —— 落点永远对到真标记上。
 */
export function estimateHitTop(height: number, offset: number, returned: number, line: number): number {
  if (!height || returned <= 0) return 0;
  const ratio = (line - (offset + 1)) / returned;
  return Math.min(1, Math.max(0, ratio)) * height;
}

/** 取离估位最近的一项。同文本多次出现时用它挑一处，而不是一律拿第一处。 */
export function nearestRange<T>(items: T[], estimateTop: number, measure: (item: T) => number): T {
  let best = items[0];
  let distance = Math.abs(measure(best) - estimateTop);
  for (const item of items.slice(1)) {
    const next = Math.abs(measure(item) - estimateTop);
    if (next < distance) {
      best = item;
      distance = next;
    }
  }
  return best;
}

function textNodes(root: Node): Text[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    nodes.push(node as Text);
  }
  return nodes;
}

/** 单个文本节点内的全部出现位置。 */
function nodeRanges(root: HTMLElement, needle: string): Range[] {
  const ranges: Range[] = [];
  for (const node of textNodes(root)) {
    for (let at = node.data.indexOf(needle); at >= 0; at = node.data.indexOf(needle, at + 1)) {
      const range = document.createRange();
      range.setStart(node, at);
      range.setEnd(node, at + needle.length);
      ranges.push(range);
    }
  }
  return ranges;
}

/**
 * 行内标记（加粗、链接、行内代码）会把一句话拆成几个文本节点，逐节点找永远找不到。
 * 这种情况在同一个块里把文本节点拼起来再找：命中「在正文里」才不落空。
 */
function blockRanges(root: HTMLElement, needle: string): Range[] {
  const ranges: Range[] = [];
  root.querySelectorAll<HTMLElement>(BLOCK_SELECTOR).forEach((block) => {
    const nodes = textNodes(block);
    if (nodes.length < 2) return;
    const starts: number[] = [];
    let joined = "";
    for (const node of nodes) {
      starts.push(joined.length);
      joined += node.data;
    }
    const locate = (index: number) => {
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        if (index >= starts[i]) return { node: nodes[i], offset: index - starts[i] };
      }
      return { node: nodes[0], offset: 0 };
    };
    for (let index = joined.indexOf(needle); index >= 0; index = joined.indexOf(needle, index + 1)) {
      const start = locate(index);
      const end = locate(index + needle.length - 1);
      const range = document.createRange();
      range.setStart(start.node, start.offset);
      range.setEnd(end.node, end.offset + 1);
      ranges.push(range);
    }
  });
  return ranges;
}

/** 把一段范围包成 mark。跨节点时逐节点各包一层（surroundContents 不接受跨越元素的范围）。 */
function markRange(range: Range): HTMLElement | null {
  const parts: Range[] = [];
  if (range.startContainer === range.endContainer) {
    parts.push(range);
  } else {
    const nodes = textNodes(range.commonAncestorContainer);
    const from = nodes.indexOf(range.startContainer as Text);
    const to = nodes.indexOf(range.endContainer as Text);
    if (from < 0 || to < 0) {
      parts.push(range);
    } else {
      for (let i = from; i <= to; i += 1) {
        const node = nodes[i];
        const begin = i === from ? range.startOffset : 0;
        const stop = i === to ? range.endOffset : node.data.length;
        if (stop <= begin) continue;
        const part = document.createRange();
        part.setStart(node, begin);
        part.setEnd(node, stop);
        parts.push(part);
      }
    }
  }
  let first: HTMLElement | null = null;
  for (const part of parts) {
    const mark = document.createElement("mark");
    // 用数据属性而不是类名标记「程序加的 mark」：正文自己也写 <mark>，
    // 清理时只能撤掉我们加的那一层，样式则统一走 .markdown-body mark。
    mark.dataset.sourceMark = "1";
    try {
      part.surroundContents(mark);
    } catch {
      continue;
    }
    if (!first) first = mark;
  }
  return first;
}

/** 一段范围相对滚动内容的坐标。Range 本身不做布局，拿它所在元素的盒子换算。 */
function rangeTop(root: HTMLElement, range: Range): number {
  const anchor = (range.startContainer as Text).parentElement ?? root;
  return anchor.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop;
}

/**
 * 在已渲染的正文里定位并标出命中，返回落点元素；找不到返回 null。
 * estimateTop 只在「同一段文本一屏里出现多次」时用来排序，选中后仍精确落到那一处。
 */
export function markNeedle(root: HTMLElement, needle: string, estimateTop = 0): HTMLElement | null {
  if (!needle) return null;
  const direct = nodeRanges(root, needle);
  const ranges = direct.length ? direct : blockRanges(root, needle);
  if (!ranges.length) return null;
  const chosen =
    ranges.length === 1 ? ranges[0] : nearestRange(ranges, estimateTop, (range) => rangeTop(root, range));
  return markRange(chosen);
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
 * 一次只读一段窗口：命中行不在已读窗口里时先取一段包含它的窗口再落地，读到的行数
 * 显示在卡片底部 —— 「跳过去了但没读那一段」不会被伪装成「已经读到了」。
 */
export function SourceReader({ source, onClose }: Props) {
  const [doc, setDoc] = useState<KnowledgeDocument | null>(null);
  const [activeHit, setActiveHit] = useState(0);
  const [jump, setJump] = useState<{ token: number; align: JumpAlign }>({ token: 0, align: "window" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  /** 读取请求的序号：连点两处命中时，先回来的那次不能覆盖后点的结果。 */
  const requestRef = useRef(0);
  /** 命中行在窗口里的估算高度，标命中时顺手记下，滚动那段在定位不到时用它兜底。 */
  const estimateRef = useRef(0);
  const hits = useMemo(() => source.hits ?? [], [source.hits]);
  const firstLine = hits[0]?.line ?? null;

  const loadWindow = useCallback(
    async (line: number | null, hitIndex: number) => {
      const offset = line === null ? 0 : Math.max(0, line - 1 - PRE_ROLL_LINES);
      const token = (requestRef.current += 1);
      setLoading(true);
      setError(null);
      setActiveHit(hitIndex);
      try {
        const next = await fetchKnowledgeDocument(source.path, offset, WINDOW_LINES);
        if (token !== requestRef.current) return;
        setDoc(next);
        // 新取的一段窗口从头看：窗口本身就从命中行上方 15 行开始，
        // 顶部同时给出「这是哪篇文档」和「命中的那一段」。
        setJump((previous) => ({ token: previous.token + 1, align: "window" }));
      } catch (failure) {
        if (token !== requestRef.current) return;
        setError(failure instanceof Error ? failure.message : String(failure));
        setDoc(null);
      } finally {
        if (token === requestRef.current) setLoading(false);
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
  // 必须是 useLayoutEffect 且排在下面那段滚动之前：同一提交里 React 按声明顺序跑布局副作用，
  // 标好命中再算落点，才落到「刚点的这一处」；用 useEffect 会晚一步，落点读到的是上一处命中。
  useLayoutEffect(() => {
    const container = bodyRef.current;
    if (!container || !doc) return;
    clearMarks(container);
    const hit = hits[activeHit];
    estimateRef.current = hit ? estimateHitTop(container.scrollHeight, doc.offset, doc.returned_lines, hit.line) : 0;
    if (!hit?.snippet) return;
    for (const candidate of highlightCandidates(hit.snippet)) {
      if (markNeedle(container, candidate, estimateRef.current)) return;
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
    if (!mark) {
      // 命中文本在渲染后的正文里定位不到（例如落在未渲染的原始 HTML 里）：退到按行号估算的
      // 高度，而不是把读者拽回窗口顶部 —— 读过好几段之后，窗口顶部离命中可能有几屏远。
      container.scrollTop = landingScrollTop(estimateRef.current);
      return;
    }
    // 用滚动容器自身的视口换算落点：offsetTop 的参照是最近的定位祖先（这里是
    // position:fixed 的 .source-view），直接拿它当 scrollTop 会多滚一个头部的高度，
    // 结果命中处被推到可视区上沿之外——「落在那一段」就落空了。
    const markTop =
      mark.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
    container.scrollTop = landingScrollTop(markTop);
  }, [jump]);

  const jumpTo = (index: number) => {
    const hit = hits[index];
    if (!hit) return;
    const loadedFrom = doc ? doc.offset + 1 : 0;
    const loadedTo = doc ? doc.offset + doc.returned_lines : 0;
    if (!doc || hit.line < loadedFrom || hit.line > loadedTo) {
      // 命中行还没读进来（在「更多」里）：先取一段包含它的窗口，落地由新窗口那一次负责。
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
    const token = (requestRef.current += 1);
    const from = doc.offset + doc.returned_lines;
    setLoading(true);
    setError(null);
    try {
      const next = await fetchKnowledgeDocument(source.path, from, WINDOW_LINES);
      if (token !== requestRef.current) return;
      setDoc({
        ...next,
        offset: doc.offset,
        content: `${doc.content}\n${next.content}`,
        returned_lines: doc.returned_lines + next.returned_lines,
      });
    } catch (failure) {
      if (token !== requestRef.current) return;
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      if (token === requestRef.current) setLoading(false);
    }
  };

  const loadedFrom = doc ? doc.offset + 1 : 0;
  const loadedTo = doc ? doc.offset + doc.returned_lines : 0;
  // 命中处数与跳转同在头部右端：命中不止一处时行号由按钮给出，胶囊只报处数；
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
          {/* 全名进 title：头部只占一行，截断的是字形不是信息。 */}
          <h1 title={doc?.title || source.title}>{doc?.title || source.title}</h1>
        </div>
        {/* 处数与跳转放在头部，不放卡片元信息行：正文滚到后面时它们仍在视野里，
            否则「这篇还命中了两处」在读过几屏之后就无从看见了。 */}
        <div className="focus-head-side">
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
          {/* 退出与集中阅读是同一套：右上角一个 ×，Esc 同义。去向唯一，不再放第二个出口。 */}
          <button type="button" className="focus-close" onClick={onClose} aria-label="退出来源阅读">
            ×
          </button>
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
