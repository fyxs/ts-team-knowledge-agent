import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createRoot, type Root } from "react-dom/client";
import App from "./main";

let container: HTMLDivElement | null = null;
let root: Root | null = null;

const CONFIG = {
  provider: "ts_proxy",
  model: "deepseek-v4-flash",
  base_url: "http://192.168.20.200:3000",
  max_tokens: 4096,
  max_steps: 8,
  api_key: "configured (****klPQ)",
};

function sseResponse(events: Record<string, unknown>[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const event of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
      }
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

async function render() {
  container = document.createElement("div");
  container.id = "root";
  document.body.appendChild(container);
  root = createRoot(container);
  root.render(<App />);
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/v1/config") && (!init || init.method === undefined || init.method === "GET")) {
        return new Response(JSON.stringify(CONFIG), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/v1/config") && init?.method === "PUT") {
        return new Response(JSON.stringify({ ...CONFIG, max_steps: 12 }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/v1/chat/stream")) {
        return sseResponse([
          { type: "start", question: "组件库架构" },
          { type: "tool_call", name: "knowledge_search", arguments: { query: "架构" } },
          { type: "tool_result", name: "knowledge_search", paths: ["members/whm/doc/doc.md"] },
          { type: "answer", content: "## 结论\n采用 Monorepo 架构。", citations: ["members/whm/doc/doc.md"] },
        ]);
      }
      return new Response("{}", { status: 404 });
    }),
  );
});

afterEach(() => {
  if (root) root.unmount();
  if (container) container.remove();
  root = null;
  container = null;
  vi.unstubAllGlobals();
});

describe("agent chat shell", () => {
  it("renders the chat interface", async () => {
    await render();
    expect(container?.textContent).toContain("TS 团队知识 Agent");
    expect(container?.querySelector("textarea")).not.toBeNull();
    expect(container?.textContent).toContain("设置");
  });

  it("shows the configured model name", async () => {
    await render();
    await flush();
    expect(container?.textContent).toContain("deepseek-v4-flash");
  });

  it("streams tool events and the final answer with citations", async () => {
    await render();
    const textarea = container?.querySelector("textarea") as HTMLTextAreaElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(textarea, "组件库架构是什么");
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    await flush();

    const button = Array.from(container?.querySelectorAll("button") ?? []).find((item) => item.textContent === "发送");
    button?.click();
    await flush();
    await flush();

    const text = container?.textContent ?? "";
    expect(text).toContain("knowledge_search");
    expect(text).toContain("采用 Monorepo 架构");
    expect(text).toContain("members/whm/doc/doc.md");
  });

  it("saves runtime settings through the config API", async () => {
    await render();
    const settingsButton = Array.from(container?.querySelectorAll("button") ?? []).find((item) => item.textContent === "设置");
    settingsButton?.click();
    await flush();

    const saveButton = Array.from(container?.querySelectorAll("button") ?? []).find((item) => item.textContent === "保存设置");
    expect(saveButton).toBeTruthy();
    saveButton?.click();
    await flush();

    expect(container?.textContent).toContain("已保存");
  });
});
