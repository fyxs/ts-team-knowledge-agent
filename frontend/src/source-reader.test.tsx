import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import App from "./App";
import { estimateHitTop, highlightCandidates, landingScrollTop, markNeedle } from "./components/SourceReader";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const DOC_PATH = "members/whm/研发指南/前端架构/前端编码规范.md";
const DOC_TITLE = "前端编码规范";
const TOTAL_LINES = 512;
const FULL_LIMIT = 100000;

/** 四处在正文里的命中：第 42 / 120 / 468 / 500 行。全文一次读进来，它们都已在正文里。 */
const FIRST_LINE = 42;
const SECOND_LINE = 120;
const THIRD_LINE = 468;
const FOURTH_LINE = 500;

const HIT_SNIPPET = "环境变量集中读取，禁止在业务代码里直接读 process.env。";
const SECOND_HIT_SNIPPET = "只有 VITE_ 前缀的变量才会被注入前端。";
const THIRD_HIT_SNIPPET = "命中行离得很远时，点行号直接滚到那一处。";
const FOURTH_HIT_SNIPPET = "连点两处命中时停在后点的那一处。";
/** 只在文档末尾才看得到的段落：用它证明整篇一次读进来了。 */
const TAIL_MARKER = "这一段在文档的末尾，只有整篇读进来才看得到。";

const SESSION = { id: "s-env", title: "环境变量怎么读取？", updatedAt: Date.now() };

const STREAM = [
  'data: {"type":"start","question":"环境变量怎么读取？"}\n\n',
  'data: {"type":"tool_call","name":"knowledge_search","arguments":{"query":"环境变量"},"step":1}\n\n',
  `data: {"type":"answer","content":"## 结论\\n\\n环境变量集中读取。","citations":["${DOC_PATH}"],` +
    `"sources":[{"path":"${DOC_PATH}","title":"${DOC_TITLE}","hits":[` +
    `{"line":${FIRST_LINE},"snippet":"${HIT_SNIPPET}"},` +
    `{"line":${SECOND_LINE},"snippet":"${SECOND_HIT_SNIPPET}"},` +
    `{"line":${THIRD_LINE},"snippet":"${THIRD_HIT_SNIPPET}"},` +
    `{"line":${FOURTH_LINE},"snippet":"${FOURTH_HIT_SNIPPET}"}]}],` +
    `"steps":1,"retrieved":true}\n\n`,
];

const FILLER = Array.from({ length: 8 }, (_, index) => `第 ${index + 1} 段正文，与命中无关。`);

const FULL_BODY = [
  `# ${DOC_TITLE}`,
  "",
  "## 环境变量",
  "",
  HIT_SNIPPET,
  "",
  "## 密钥",
  "",
  SECOND_HIT_SNIPPET,
  "",
  "## 长文之后",
  "",
  ...FILLER,
  "",
  THIRD_HIT_SNIPPET,
  "",
  FOURTH_HIT_SNIPPET,
  "",
  TAIL_MARKER,
].join("\n");

/** 命中片段 → 它在渲染结果里的高度，用来反推「落到了哪一处」。 */
const TOPS: Record<string, number> = {
  [HIT_SNIPPET]: 300,
  [SECOND_HIT_SNIPPET]: 6000,
  [THIRD_HIT_SNIPPET]: 9000,
  [FOURTH_HIT_SNIPPET]: 12000,
};

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

let container: HTMLDivElement | null = null;
let root: Root | null = null;
let docRequests: string[] = [];

function handler(url: string): Response | Promise<Response> {
  const json = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200 });
  if (url.includes("/api/v1/chat/stream")) return sseResponse(STREAM);
  if (url.includes("/api/v1/knowledge/document")) {
    docRequests.push(url);
    const offset = Number(new URL(url, "http://localhost").searchParams.get("offset") ?? 0);
    return json({
      path: DOC_PATH,
      title: DOC_TITLE,
      content: FULL_BODY,
      offset,
      returned_lines: TOTAL_LINES,
      total_lines: TOTAL_LINES,
      truncated: false,
    });
  }
  if (url.includes("/api/v1/sessions/")) return json({ session: SESSION, messages: [] });
  if (url.includes("/api/v1/sessions")) return json({ sessions: [SESSION] });
  if (url.includes("/api/v1/run")) return json({ running: false, started_at: null, last: null, report: null });
  if (url.includes("/api/v1/config")) {
    return json({
      provider: "ts_proxy",
      model: "deepseek-v4-flash",
      base_url: "",
      max_tokens: 4096,
      max_steps: 8,
      scan_interval_minutes: 60,
      api_key: "configured (****klPQ)",
    });
  }
  return json({});
}

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => Promise.resolve(handler(typeof input === "string" ? input : String(input)))),
  );
}

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function ask() {
  await act(async () => {
    root?.render(<App />);
  });
  await flush();
  const textarea = container?.querySelector("textarea") as HTMLTextAreaElement;
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
  await act(async () => {
    setter?.call(textarea, "环境变量怎么读取？");
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await flush();
  await act(async () => {
    (container?.querySelector(".composer button") as HTMLButtonElement).click();
  });
  await flush();
  await flush();
}

function pressEscape() {
  return act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
}

/** 阅读层要用的元素属性是临时改到 Element.prototype 上的，逐个记下来，用例结束再还回去。 */
const patched: Array<{ prop: string; descriptor: PropertyDescriptor | undefined }> = [];

function patchElement(prop: string, descriptor: PropertyDescriptor) {
  patched.push({ prop, descriptor: Object.getOwnPropertyDescriptor(Element.prototype, prop) });
  Object.defineProperty(Element.prototype, prop, { configurable: true, ...descriptor });
}

beforeEach(() => {
  docRequests = [];
  localStorage.clear();
  document.documentElement.dataset.theme = "dark";
  window.history.replaceState({}, "", "/");
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  stubFetch();
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  while (patched.length) {
    const { prop, descriptor } = patched.pop()!;
    if (descriptor) Object.defineProperty(Element.prototype, prop, descriptor);
    else delete (Element.prototype as unknown as Record<string, unknown>)[prop];
  }
  vi.unstubAllGlobals();
  // 落点测试往 Element.prototype 上打过桩：不还原会渗到后面的用例里。
  vi.restoreAllMocks();
});

const reader = () => container?.querySelector(".source-view") as HTMLElement | null;

/**
 * jsdom 不做排版：滚动落点只能喂桩。滚动区高 800、顶部在内容坐标 0；
 * 每一处命中标记的高度由 TOPS 给 —— 于是「落到了哪一处」可以从最终的 scrollTop 反推。
 *
 * 桩装在 Element.prototype 上，所以**可以在打开阅读层之前就装好** —— 首次落点发生在
 * 文档进来的那一提交里，晚装就看不到了。
 */
function stubScroll() {
  let scrollTop = 0;
  const rect = (top: number) =>
    ({ top, bottom: top + 22, left: 0, right: 0, width: 0, height: 22, x: 0, y: top, toJSON: () => ({}) }) as DOMRect;
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    if (this.classList.contains("messages")) return rect(0);
    if (this.matches("mark[data-source-mark]")) {
      const mark = this as HTMLElement;
      const top = Object.entries(TOPS).find(([snippet]) =>
        highlightCandidates(snippet).some((candidate) => (mark.textContent ?? "").includes(candidate)),
      );
      // 标记的视口坐标随滚动上移：喂桩也要照这个来，否则落点会把已经滚过的那一段再加一遍。
      return rect((top ? top[1] : 400) - scrollTop);
    }
    return rect(40);
  });
  patchElement("clientHeight", {
    get() {
      return 800;
    },
  });
  patchElement("scrollHeight", {
    get() {
      return 24000;
    },
  });
  patchElement("scrollTop", {
    get() {
      return scrollTop;
    },
    set(value: number) {
      scrollTop = value;
    },
  });
  return {
    get value() {
      return scrollTop;
    },
  };
}

/** 这一处标记是不是某条命中标出来的：拿候选串认人，别硬编码整条 snippet。 */
function isMarkOf(mark: HTMLElement, snippet: string): boolean {
  return highlightCandidates(snippet).some((candidate) => (mark.textContent ?? "").includes(candidate));
}

async function openReader() {
  await ask();
  await act(async () => {
    container?.querySelector<HTMLButtonElement>(".citation-row")?.click();
  });
  await flush();
}

/** 行号按钮上的「当前落点」标记：用户点过的那一处才带 is-active。 */
const markedHits = () =>
  [...(reader()?.querySelectorAll<HTMLButtonElement>(".source-hit.is-active") ?? [])].map(
    (button) => button.textContent,
  );

async function clickHit(index: number) {
  await act(async () => {
    reader()?.querySelectorAll<HTMLButtonElement>(".source-hit")[index].click();
  });
  await flush();
}

describe("citation source reader", () => {
  it("makes every citation row clickable and shows where the hit is", async () => {
    await ask();

    const text = container?.querySelector(".citation")?.textContent ?? "";
    expect(text).toContain(DOC_TITLE);
    expect(text).toContain(`命中 4 处 · 第 ${FIRST_LINE} 行`);
    // 完整路径不进列表行：它只出现在 title 提示与阅读层头部
    const row = container?.querySelector<HTMLButtonElement>(".citation-row");
    expect(row?.getAttribute("title")).toBe(DOC_PATH);
  });

  it("loads the whole document in one request and lands on the first hit", async () => {
    const scroll = stubScroll();
    await openReader();

    // 一次读全文：offset 0、上限跟服务层一致，没有第二次请求
    expect(docRequests.length).toBe(1);
    expect(docRequests[0]).toContain("/api/v1/knowledge/document?");
    expect(docRequests[0]).toContain("offset=0");
    expect(docRequests[0]).toContain(`limit=${FULL_LIMIT}`);

    const view = reader();
    expect(view).not.toBeNull();
    const body = view?.querySelector(".source-doc")?.textContent ?? "";
    // 开头的、末尾的都在正文里 —— 这就是「一次展全文」
    expect(body).toContain("环境变量集中读取");
    expect(body).toContain(TAIL_MARKER);
    // 没有分页残留：没有「继续读取下方」、没有读数行、没有页脚
    expect(view?.querySelector(".source-more")).toBeNull();
    expect(view?.querySelector(".source-foot")).toBeNull();
    expect(view?.querySelector(".source-progress")).toBeNull();
    expect(view?.textContent).not.toContain("继续读取");

    // 文档名占满头部左侧：省略号只截字形，全名进 title 提示
    const heading = view?.querySelector<HTMLElement>(".focus-head h1");
    expect(heading?.textContent).toBe(DOC_TITLE);
    expect(heading?.getAttribute("title")).toBe(DOC_TITLE);
    expect(view?.querySelector(".source-path")?.textContent).toBe(DOC_PATH);
    expect(view?.querySelector<HTMLButtonElement>(".focus-head .focus-close")?.getAttribute("aria-label")).toBe(
      "退出来源阅读",
    );
    // 处数与跳转都在头部右端：处数是值，行号按钮是去处
    expect(view?.querySelector(".focus-head-side .source-hit-chip")?.textContent).toBe("命中 4 处");
    const jumpButtons = view?.querySelectorAll<HTMLButtonElement>(".focus-head-side .source-hit");
    expect(jumpButtons?.length).toBe(4);
    expect(jumpButtons?.[0].textContent).toBe(`第 ${FIRST_LINE} 行`);
    // 进来是自动落在第 1 处，那是落点不是选择：按钮一处都不预选。
    expect([...(jumpButtons ?? [])].every((button) => button.getAttribute("aria-current") === "false")).toBe(true);
    expect(view?.querySelectorAll(".source-hit.is-active").length).toBe(0);
    // 卡片元信息行只留身份：路径 + 类型与行数，命中信息不再挂在这里
    expect(view?.querySelector(".source-doc-meta .source-hit-chip")).toBeNull();
    expect(view?.querySelector(".source-doc-meta")?.textContent).toContain(DOC_PATH);
    expect(view?.querySelector(".source-doc-meta")?.textContent).toContain(`共 ${TOTAL_LINES} 行`);

    // 自动落点是「第 1 处命中那一行」，不是文档顶部
    expect(scroll.value).toBe(TOPS[HIT_SNIPPET] - 24);
    const mark = view?.querySelector("mark[data-source-mark]");
    expect(mark?.textContent).toBeTruthy();
    expect(HIT_SNIPPET).toContain(mark?.textContent ?? "");
  });

  it("keeps the hit count and the jump buttons in the header, outside the scrolling body", async () => {
    await openReader();

    const view = reader();
    // 头部不在滚动区里——这就是「滚到下面也找得到」的依据：正文再怎么滚，头部不动
    const head = view?.querySelector(".focus-head");
    expect(head).not.toBeNull();
    expect(head?.closest(".messages")).toBeNull();
    const side = view?.querySelector(".focus-head-side");
    expect(side).not.toBeNull();
    expect(side?.closest(".messages")).toBeNull();
    expect(side?.querySelector(".source-hit-chip")?.textContent).toBe("命中 4 处");

    // 一处不漏：放不下时由跳转条自己横向滚动，而不是吞掉后面的按钮
    const buttons = [...(view?.querySelectorAll<HTMLButtonElement>(".source-hits .source-hit") ?? [])];
    expect(buttons.map((button) => button.textContent)).toEqual([
      `第 ${FIRST_LINE} 行`,
      `第 ${SECOND_LINE} 行`,
      `第 ${THIRD_LINE} 行`,
      `第 ${FOURTH_LINE} 行`,
    ]);

    // 头部右端是一组：处数 → 跳转 → ×，× 始终在最右、始终在最后
    expect(side?.firstElementChild?.classList.contains("source-hit-chip")).toBe(true);
    expect(side?.lastElementChild?.classList.contains("focus-close")).toBe(true);
    expect(view?.querySelector(".source-hits")?.nextElementSibling?.classList.contains("focus-close")).toBe(true);

    // 卡片元信息行只剩身份，不再参与命中跳转
    expect(view?.querySelector(".source-doc-meta .source-hit")).toBeNull();
  });

  it("scrolls to every hit in the fully loaded document without fetching it again", async () => {
    const scroll = stubScroll();
    await openReader();

    const cases: Array<[number, string, number]> = [
      [0, HIT_SNIPPET, FIRST_LINE],
      [1, SECOND_HIT_SNIPPET, SECOND_LINE],
      [2, THIRD_HIT_SNIPPET, THIRD_LINE],
      [3, FOURTH_HIT_SNIPPET, FOURTH_LINE],
    ];
    for (const [index, snippet, line] of cases) {
      await clickHit(index);
      // 全文已经在正文里：跳转不取文档，只有打开那一次请求
      expect(docRequests.length).toBe(1);
      expect(scroll.value).toBe(TOPS[snippet] - 24);
      expect(markedHits()).toEqual([`第 ${line} 行`]);
      const mark = reader()?.querySelector("mark[data-source-mark]") as HTMLElement | null;
      expect(mark).not.toBeNull();
      expect(isMarkOf(mark as HTMLElement, snippet)).toBe(true);
    }
  });

  it("stays on the hit you clicked last when two jumps are close together", async () => {
    const scroll = stubScroll();
    await openReader();

    await clickHit(2);
    await clickHit(3);

    expect(docRequests.length).toBe(1);
    expect(scroll.value).toBe(TOPS[FOURTH_HIT_SNIPPET] - 24);
    expect(markedHits()).toEqual([`第 ${FOURTH_LINE} 行`]);
  });

  it("closes the reader with Escape and leaves the focus view open", async () => {
    await ask();
    await act(async () => {
      container?.querySelector<HTMLButtonElement>(".message-open")?.click();
    });
    await flush();
    expect(container?.querySelector(".focus-view")).not.toBeNull();

    await act(async () => {
      container?.querySelector<HTMLButtonElement>(".focus-view .citation-row")?.click();
    });
    await flush();
    expect(reader()).not.toBeNull();

    await pressEscape();
    await flush();
    // 一次 Esc 只退一层：来源层关掉，集中阅读还在
    expect(reader()).toBeNull();
    expect(container?.querySelector(".focus-view")).not.toBeNull();

    await pressEscape();
    await flush();
    expect(container?.querySelector(".focus-view")).toBeNull();
  });

  it("exits from the same × as the answer reader, with no second back button", async () => {
    await ask();
    await act(async () => {
      container?.querySelector<HTMLButtonElement>(".message-open")?.click();
    });
    await flush();
    await act(async () => {
      container?.querySelector<HTMLButtonElement>(".focus-view .citation-row")?.click();
    });
    await flush();

    const view = reader();
    expect(view).not.toBeNull();
    expect(view?.querySelector(".source-back")).toBeNull();

    await act(async () => {
      view?.querySelector<HTMLButtonElement>(".focus-close")?.click();
    });
    await flush();
    // 退出后回到集中阅读，而不是一路退到会话列表
    expect(reader()).toBeNull();
    expect(container?.querySelector(".focus-view")).not.toBeNull();
  });

  it("keeps the landing math honest", () => {
    // 命中处对到顶部留白处
    expect(landingScrollTop(6000)).toBe(5976);
    // 靠近文档开头：不越过内容顶端
    expect(landingScrollTop(10)).toBe(0);
    expect(landingScrollTop(24)).toBe(0);
  });

  it("estimates where the hit line sits, for ranking and for the no-mark fallback", () => {
    // 整篇 512 行：第 257 行在一半处
    expect(estimateHitTop(600, 0, 512, 257)).toBeCloseTo(300, 0);
    // 从第 27 行开始读的那种窗口：同一行号要按窗口起点折算
    expect(estimateHitTop(600, 26, 300, 177)).toBe(300);
    // 边界：命中在窗口第一行、行号超出已读行数、以及还没有排版高度时都不出错
    expect(estimateHitTop(600, 0, 300, 1)).toBe(0);
    expect(estimateHitTop(600, 0, 300, 9999)).toBe(600);
    expect(estimateHitTop(0, 0, 300, 100)).toBe(0);
  });

  it("marks a hit whose sentence is split by inline markup", () => {
    const host = document.createElement("div");
    host.innerHTML = "<p><strong>环境变量集中读取</strong>，禁止在业务代码里直接读 <code>process.env</code>。</p>";

    // 加粗 / 行内代码把一句话拆成几个文本节点：逐节点找必然落空，要在块内拼起来找
    const mark = markNeedle(host, "读取，禁止");
    expect(mark).not.toBeNull();
    expect(mark?.textContent).toBe("读取");
    expect(host.querySelectorAll("mark[data-source-mark]").length).toBe(2);

    // 真的没有的串就返回 null，不能随手标一处交差
    expect(markNeedle(host, "这一段文档里没有")).toBeNull();
  });

  it("picks the occurrence nearest the hit line when the same sentence appears twice", () => {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      const top = Number((this as HTMLElement).dataset.top ?? 0);
      return { top, bottom: top + 22, left: 0, right: 0, width: 0, height: 22, x: 0, y: top, toJSON: () => ({}) } as DOMRect;
    });
    const body = () => {
      const host = document.createElement("div");
      host.innerHTML =
        '<p data-top="80">同一句话在文里出现两次。</p><p data-top="5000">同一句话在文里出现两次。</p>';
      return host;
    };

    // 短锚点（「同一句话」这种）在一屏里会出现多次：取离命中行最近的那一处，而不是一律拿第一处
    expect(markNeedle(body(), "同一句话", 80)?.closest("p")?.getAttribute("data-top")).toBe("80");
    expect(markNeedle(body(), "同一句话", 5000)?.closest("p")?.getAttribute("data-top")).toBe("5000");
  });

  it("reports a read failure instead of showing an empty document", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : String(input);
        if (url.includes("/api/v1/knowledge/document")) return Promise.resolve(new Response("gone", { status: 404 }));
        return Promise.resolve(handler(url));
      }),
    );
    await ask();
    await act(async () => {
      container?.querySelector<HTMLButtonElement>(".citation-row")?.click();
    });
    await flush();

    expect(reader()?.querySelector(".source-status-error")?.textContent).toContain("读取失败");
  });
});
