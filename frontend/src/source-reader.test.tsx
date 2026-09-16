import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import App from "./App";
import { landingScrollTop } from "./components/SourceReader";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const DOC_PATH = "members/whm/研发指南/前端架构/前端编码规范.md";
const DOC_TITLE = "前端编码规范";
const FIRST_LINE = 42;
/** 同一篇文档里的第二处命中：用来验证窗口内的跳转真的会滚动，而不是停在原处。 */
const SECOND_LINE = 120;
/** 阅读层要从命中行上方 15 行开始取，而不是从文档开头开始。 */
const FIRST_OFFSET = FIRST_LINE - 1 - 15;
const WINDOW_LINES = 300;
const SECOND_OFFSET = FIRST_OFFSET + WINDOW_LINES;
const TOTAL_LINES = 512;
const HIT_SNIPPET = "环境变量集中读取，禁止在业务代码里直接读 process.env。";
const SECOND_HIT_SNIPPET = "只有 VITE_ 前缀的变量才会被注入前端。";

const SESSION = { id: "s-env", title: "环境变量怎么读取？", updatedAt: Date.now() };

const STREAM = [
  'data: {"type":"start","question":"环境变量怎么读取？"}\n\n',
  'data: {"type":"tool_call","name":"knowledge_search","arguments":{"query":"环境变量"},"step":1}\n\n',
  `data: {"type":"answer","content":"## 结论\\n\\n环境变量集中读取。","citations":["${DOC_PATH}"],` +
    `"sources":[{"path":"${DOC_PATH}","title":"${DOC_TITLE}","hits":[{"line":${FIRST_LINE},"snippet":"${HIT_SNIPPET}"},{"line":${SECOND_LINE},"snippet":"${SECOND_HIT_SNIPPET}"}]}],` +
    `"steps":1,"retrieved":true}\n\n`,
];

const FIRST_WINDOW_BODY = `# ${DOC_TITLE}\n\n## 环境变量\n\n${HIT_SNIPPET}\n\n## 密钥\n\n只有 VITE_ 前缀的变量才会被注入前端。\n`;
const SECOND_WINDOW_BODY = `# ${DOC_TITLE}\n\n## 窗口之外\n\n这一段在第一次读取的窗口之外。\n`;

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

function handler(url: string): Response {
  const json = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200 });
  if (url.includes("/api/v1/chat/stream")) return sseResponse(STREAM);
  if (url.includes("/api/v1/knowledge/document")) {
    docRequests.push(url);
    const offset = Number(new URL(url, "http://localhost").searchParams.get("offset") ?? 0);
    const append = offset >= SECOND_OFFSET;
    return json({
      path: DOC_PATH,
      title: DOC_TITLE,
      content: append ? SECOND_WINDOW_BODY : FIRST_WINDOW_BODY,
      offset,
      returned_lines: append ? 8 : WINDOW_LINES,
      total_lines: TOTAL_LINES,
      truncated: !append,
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
  vi.unstubAllGlobals();
});

const reader = () => container?.querySelector(".source-view") as HTMLElement | null;

describe("citation source reader", () => {
  it("makes every citation row clickable and shows where the hit is", async () => {
    await ask();

    const text = container?.querySelector(".citation")?.textContent ?? "";
    expect(text).toContain(DOC_TITLE);
    expect(text).toContain(`命中 2 处 · 第 ${FIRST_LINE} 行`);
    // 完整路径不进列表行：它只出现在 title 提示与阅读层头部
    const row = container?.querySelector<HTMLButtonElement>(".citation-row");
    expect(row?.getAttribute("title")).toBe(DOC_PATH);
  });

  it("opens the document at the hit line, not at the top of the file", async () => {
    await ask();

    await act(async () => {
      container?.querySelector<HTMLButtonElement>(".citation-row")?.click();
    });
    await flush();

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
    expect(view?.querySelector(".source-doc-meta .source-hit-chip")?.textContent).toBe("命中 2 处");
    const jumpButtons = view?.querySelectorAll<HTMLButtonElement>(".source-doc-meta .source-hit");
    expect(jumpButtons?.length).toBe(2);
    expect(jumpButtons?.[0].textContent).toBe(`第 ${FIRST_LINE} 行`);
    expect(jumpButtons?.[0].getAttribute("aria-pressed")).toBe("true");
    expect(view?.querySelector(".source-doc")?.textContent).toContain("环境变量集中读取");

    // 命中片段在正文里被标出来，阅读层不是只给一个行号
    const mark = view?.querySelector("mark[data-source-mark]");
    expect(mark?.textContent).toBeTruthy();
    expect(HIT_SNIPPET).toContain(mark?.textContent ?? "");
  });

  it("continues reading below the loaded window and keeps the hit marked", async () => {
    await ask();
    await act(async () => {
      container?.querySelector<HTMLButtonElement>(".citation-row")?.click();
    });
    await flush();

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
    await ask();
    await act(async () => {
      container?.querySelector<HTMLButtonElement>(".citation-row")?.click();
    });
    await flush();

    // jsdom 不做排版，落点只能喂桩：滚动区高 800，命中处在内容坐标 6000。
    const messages = reader()?.querySelector<HTMLElement>(".messages");
    let scrollTop = 0;
    const rect = (top: number) =>
      ({ top, bottom: top + 22, left: 0, right: 0, width: 0, height: 22, x: 0, y: top, toJSON: () => ({}) }) as DOMRect;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      if (this.classList.contains("messages")) return rect(0);
      return rect(this.matches("mark[data-source-mark]") ? 6000 : 40);
    });
    Object.defineProperty(messages, "clientHeight", {
      configurable: true,
      get() {
        return 800;
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

    await act(async () => {
      reader()?.querySelectorAll<HTMLButtonElement>(".source-hit")[1].click();
    });
    await flush();

    // 命中处对到滚动区顶部留白处：6000 − 24。上一版把它钳在卡片顶端，点了几近等于没反应。
    expect(scrollTop).toBe(6000 - 24);
    expect(reader()?.querySelectorAll(".source-hit")[1].getAttribute("aria-pressed")).toBe("true");
  });

  it("keeps the landing math honest", () => {
    // 命中处对到顶部留白处
    expect(landingScrollTop(6000)).toBe(5976);
    // 靠近文档开头：不越过内容顶端
    expect(landingScrollTop(10)).toBe(0);
    expect(landingScrollTop(24)).toBe(0);
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
