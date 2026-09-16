import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import App from "./App";
import { estimateHitTop, highlightCandidates, landingScrollTop, markNeedle } from "./components/SourceReader";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const DOC_PATH = "members/whm/研发指南/前端架构/前端编码规范.md";
const DOC_TITLE = "前端编码规范";
const WINDOW_LINES = 300;
const TOTAL_LINES = 512;

/** 已读窗口里的两处命中：窗口内的跳转要滚动，而不是重取。 */
const FIRST_LINE = 42;
const SECOND_LINE = 120;
/** 已读窗口之外的两处命中：点它们必须先取一段包含命中行的窗口——「命中在更多里」的那条路。 */
const THIRD_LINE = 468;
const FOURTH_LINE = 500;

/** 阅读层要从命中行上方 15 行开始取，而不是从文档开头开始。 */
const FIRST_OFFSET = FIRST_LINE - 1 - 15; // 26 → 读第 27–326 行
const SECOND_OFFSET = FIRST_OFFSET + WINDOW_LINES; // 326 → 继续读取下方从这里接
const THIRD_OFFSET = THIRD_LINE - 1 - 15; // 452 → 跳第 468 行要先取这一段
const FOURTH_OFFSET = FOURTH_LINE - 1 - 15; // 484

const HIT_SNIPPET = "环境变量集中读取，禁止在业务代码里直接读 process.env。";
const SECOND_HIT_SNIPPET = "只有 VITE_ 前缀的变量才会被注入前端。";
const THIRD_HIT_SNIPPET = "命中落在已读窗口之外时先取一段包含它的窗口。";
const FOURTH_HIT_SNIPPET = "连续点两处命中时后一次读取接管。";

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

const FIRST_WINDOW_BODY = `# ${DOC_TITLE}\n\n## 环境变量\n\n${HIT_SNIPPET}\n\n## 密钥\n\n${SECOND_HIT_SNIPPET}\n`;
const APPEND_BODY = `## 追加段\n\n这一段在第一次读取的窗口之外。\n\n${THIRD_HIT_SNIPPET}\n\n${FOURTH_HIT_SNIPPET}\n`;
const THIRD_WINDOW_BODY = `## 再往后\n\n${THIRD_HIT_SNIPPET}\n`;
const FOURTH_WINDOW_BODY = `## 更靠后\n\n${FOURTH_HIT_SNIPPET}\n`;

type DocWindow = { content: string; returned_lines: number; truncated: boolean };

/** 后端按 offset 返回的那一段窗口。档位与真实接口一致：从 offset 起最多 limit 行。 */
const WINDOWS: Record<number, DocWindow> = {
  [FIRST_OFFSET]: { content: FIRST_WINDOW_BODY, returned_lines: WINDOW_LINES, truncated: true },
  [SECOND_OFFSET]: { content: APPEND_BODY, returned_lines: TOTAL_LINES - SECOND_OFFSET, truncated: false },
  [THIRD_OFFSET]: { content: THIRD_WINDOW_BODY, returned_lines: TOTAL_LINES - THIRD_OFFSET, truncated: false },
  [FOURTH_OFFSET]: { content: FOURTH_WINDOW_BODY, returned_lines: TOTAL_LINES - FOURTH_OFFSET, truncated: false },
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
/** 需要造「后点的先回来」时，把某几段窗口的响应扣在这里，等测试放行。 */
let heldOffsets: number[] = [];
let heldResponses: Array<() => void> = [];

function releaseHeld() {
  const pending = heldResponses;
  heldOffsets = [];
  heldResponses = [];
  pending.forEach((release) => release());
}

function handler(url: string): Response | Promise<Response> {
  const json = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200 });
  if (url.includes("/api/v1/chat/stream")) return sseResponse(STREAM);
  if (url.includes("/api/v1/knowledge/document")) {
    docRequests.push(url);
    const offset = Number(new URL(url, "http://localhost").searchParams.get("offset") ?? 0);
    const window = WINDOWS[offset] ?? { content: "", returned_lines: 0, truncated: false };
    const payload = { path: DOC_PATH, title: DOC_TITLE, offset, total_lines: TOTAL_LINES, ...window };
    if (heldOffsets.includes(offset)) {
      return new Promise<Response>((resolve) => {
        heldResponses.push(() => resolve(json(payload)));
      });
    }
    return json(payload);
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

beforeEach(() => {
  docRequests = [];
  heldOffsets = [];
  heldResponses = [];
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
  vi.unstubAllGlobals();
  // 落点测试往 Element.prototype 上打过桩：不还原会渗到后面的用例里。
  vi.restoreAllMocks();
});

const reader = () => container?.querySelector(".source-view") as HTMLElement | null;

/**
 * jsdom 不做排版：滚动落点只能喂桩。滚动区高 800、顶部在内容坐标 0；
 * 每一处命中标记的高度由 topOfMark 给 —— 于是「落到了哪一处」可以从最终的 scrollTop 反推。
 */
function stubScroll(topOfMark: (mark: HTMLElement) => number) {
  const messages = reader()?.querySelector<HTMLElement>(".messages");
  if (!messages) throw new Error("阅读层还没打开，没法给滚动落点喂桩");
  let scrollTop = 0;
  const rect = (top: number) =>
    ({ top, bottom: top + 22, left: 0, right: 0, width: 0, height: 22, x: 0, y: top, toJSON: () => ({}) }) as DOMRect;
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    if (this.classList.contains("messages")) return rect(0);
    if (this.matches("mark[data-source-mark]")) return rect(topOfMark(this as HTMLElement));
    return rect(40);
  });
  Object.defineProperty(messages, "clientHeight", {
    configurable: true,
    get() {
      return 800;
    },
  });
  Object.defineProperty(messages, "scrollHeight", {
    configurable: true,
    get() {
      return 24000;
    },
  });
  Object.defineProperty(messages, "scrollTop", {
    configurable: true,
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

  it("opens the document at the hit line, not at the top of the file", async () => {
    await openReader();

    expect(docRequests.length).toBe(1);
    expect(docRequests[0]).toContain("/api/v1/knowledge/document?");
    expect(docRequests[0]).toContain(`offset=${FIRST_OFFSET}`);

    const view = reader();
    expect(view).not.toBeNull();
    expect(view?.querySelector("h1")?.textContent).toBe(DOC_TITLE);
    expect(view?.querySelector(".source-path")?.textContent).toBe(DOC_PATH);
    // 头部只剩「来源 + 文档名 + ×」：胶囊不再挂在头部
    expect(view?.querySelector(".focus-head .source-hit-chip")).toBeNull();
    expect(view?.querySelector<HTMLButtonElement>(".focus-head .focus-close")?.getAttribute("aria-label")).toBe(
      "退出来源阅读",
    );
    // 命中信息与跳转同在卡片元信息行右端：处数是值，行号按钮是去处
    expect(view?.querySelector(".source-doc-meta .source-hit-chip")?.textContent).toBe("命中 4 处");
    const jumpButtons = view?.querySelectorAll<HTMLButtonElement>(".source-doc-meta .source-hit");
    expect(jumpButtons?.length).toBe(4);
    expect(jumpButtons?.[0].textContent).toBe(`第 ${FIRST_LINE} 行`);
    expect(jumpButtons?.[0].getAttribute("aria-pressed")).toBe("true");
    expect(view?.querySelector(".source-doc")?.textContent).toContain("环境变量集中读取");

    // 命中片段在正文里被标出来，阅读层不是只给一个行号
    const mark = view?.querySelector("mark[data-source-mark]");
    expect(mark?.textContent).toBeTruthy();
    expect(HIT_SNIPPET).toContain(mark?.textContent ?? "");
  });

  it("continues reading below the loaded window and keeps the hit marked", async () => {
    await openReader();

    expect(reader()?.querySelector(".source-progress")?.textContent).toContain(`共 ${TOTAL_LINES} 行`);
    await act(async () => {
      reader()?.querySelector<HTMLButtonElement>(".source-more")?.click();
    });
    await flush();

    expect(docRequests.length).toBe(2);
    expect(docRequests[1]).toContain(`offset=${SECOND_OFFSET}`);
    const body = reader()?.querySelector(".source-doc")?.textContent ?? "";
    expect(body).toContain("环境变量集中读取");
    expect(body).toContain("这一段在第一次读取的窗口之外");
    expect(reader()?.querySelector(".source-progress-end")?.textContent).toContain("已读到文档末尾");
    // 追加读取不该把命中标记弄丢，也不该把读者拽回命中行
    expect(reader()?.querySelector("mark[data-source-mark]")?.textContent).toBeTruthy();
  });

  it("jumps to a hit beyond the loaded window by fetching a window around it", async () => {
    await openReader();
    // 长文的常态：命中的那一行在「更多」里，还没读进来。
    const scroll = stubScroll(() => 300);

    await clickHit(2);

    expect(docRequests.length).toBe(2);
    expect(docRequests[1]).toContain(`offset=${THIRD_OFFSET}`);
    expect(docRequests[1]).toContain(`limit=${WINDOW_LINES}`);
    // 新取的一段窗口回到内容顶部：命中行就在上方 15 行预读之后，落在视野里
    expect(scroll.value).toBe(0);
    const body = reader()?.querySelector(".source-doc")?.textContent ?? "";
    expect(body).toContain(THIRD_HIT_SNIPPET);
    expect(body).not.toContain("环境变量集中读取");
    // 新窗口里这一处命中同样被标出来，不是只有窗口顶部
    const mark = reader()?.querySelector("mark[data-source-mark]");
    expect(mark?.textContent).toBeTruthy();
    expect(isMarkOf(mark as HTMLElement, THIRD_HIT_SNIPPET)).toBe(true);
    expect(reader()?.querySelectorAll(".source-hit")[2].getAttribute("aria-pressed")).toBe("true");
    // 读数跟着新窗口走：跳到第 453 行往后，不是「已经读到过前面」
    expect(reader()?.querySelector(".source-progress-end")?.textContent).toContain(`共 ${TOTAL_LINES} 行`);
  });

  it("does not refetch a hit that 继续读取 has already pulled into the window", async () => {
    await openReader();
    const scroll = stubScroll((mark) => (isMarkOf(mark, THIRD_HIT_SNIPPET) ? 5000 : 300));

    await act(async () => {
      reader()?.querySelector<HTMLButtonElement>(".source-more")?.click();
    });
    await flush();
    expect(docRequests.length).toBe(2);

    // 继续读下来之后第 468 行已经在已读窗口里：这一跳不该再取文档，直接滚到那一处
    await clickHit(2);

    expect(docRequests.length).toBe(2);
    expect(scroll.value).toBe(5000 - 24);
    expect(reader()?.querySelectorAll(".source-hit")[2].getAttribute("aria-pressed")).toBe("true");
  });

  it("keeps the hit you clicked last when two reads are in flight", async () => {
    await openReader();
    stubScroll((mark) => (isMarkOf(mark, FOURTH_HIT_SNIPPET) ? 9000 : 300));

    // 第一跳的响应先扣住不给：模拟网络慢，后点的先回来了
    heldOffsets = [THIRD_OFFSET];
    await clickHit(2);
    await clickHit(3);
    expect(docRequests.length).toBe(3);
    expect(reader()?.querySelector(".source-doc")?.textContent).toContain(FOURTH_HIT_SNIPPET);

    // 放行那次过时的响应：它不能把读者拽回上一处命中
    releaseHeld();
    await flush();
    const body = reader()?.querySelector(".source-doc")?.textContent ?? "";
    expect(body).toContain(FOURTH_HIT_SNIPPET);
    expect(body).not.toContain(THIRD_HIT_SNIPPET);
    expect(reader()?.querySelectorAll(".source-hit")[3].getAttribute("aria-pressed")).toBe("true");
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

  it("scrolls to a hit inside the loaded window instead of staying put", async () => {
    await openReader();
    // 两处命中给两个高度：落到第二处是 6000，落到第一处（= 落点还在读上一处命中）是 300。
    const scroll = stubScroll((mark) => (isMarkOf(mark, SECOND_HIT_SNIPPET) ? 6000 : 300));

    await clickHit(1);

    // 命中处对到滚动区顶部留白处：6000 − 24。上一版把它钳在卡片顶端，点了几近等于没反应。
    expect(scroll.value).toBe(6000 - 24);
    expect(reader()?.querySelectorAll(".source-hit")[1].getAttribute("aria-pressed")).toBe("true");
  });

  it("keeps the landing math honest", () => {
    // 命中处对到顶部留白处
    expect(landingScrollTop(6000)).toBe(5976);
    // 靠近文档开头：不越过内容顶端
    expect(landingScrollTop(10)).toBe(0);
    expect(landingScrollTop(24)).toBe(0);
  });

  it("estimates where the hit line sits in the window, for ranking and for the no-mark fallback", () => {
    // 窗口从第 1 行起共 300 行：第 151 行在一半处
    expect(estimateHitTop(600, 0, 300, 151)).toBe(300);
    // 窗口从第 27 行起：同一行号要按窗口起点折算
    expect(estimateHitTop(600, 26, 300, 177)).toBe(300);
    // 边界：命中在窗口第一行、在窗口之外、以及还没有排版高度时都不出错
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
    expect(markNeedle(body(), "同一句话", 0)?.closest("p")?.getAttribute("data-top")).toBe("80");
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
