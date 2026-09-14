import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import App from "./App";

// React 18 在测试环境需要显式声明，否则状态更新不会同步刷新。
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const CONFIG = {
  provider: "ts_proxy",
  model: "deepseek-v4-flash",
  base_url: "http://192.168.20.200:3000",
  max_tokens: 4096,
  max_steps: 8,
  api_key: "configured (****klPQ)",
};

const STREAM = [
  'data: {"type":"start","question":"架构？"}\n\n',
  'data: {"type":"tool_call","name":"knowledge_search","arguments":{"query":"组件库 架构"},"step":1}\n\n',
  'data: {"type":"tool_result","name":"knowledge_search","summary":"命中 3 条","step":1}\n\n',
  'data: {"type":"tool_call","name":"knowledge_read","arguments":{"path":"members/whm/a/a.md"},"step":2}\n\n',
  'data: {"type":"tool_result","name":"knowledge_read","summary":"读取 200 行","step":2}\n\n',
  'data: {"type":"answer","content":"## 结论\\n\\n组件库是 **Monorepo**。","citations":["members/whm/a/a.md"],"steps":2}\n\n',
];

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

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  vi.unstubAllGlobals();
});

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function stubFetch(handler: (url: string, init?: RequestInit) => Response) {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : String(input);
    return Promise.resolve(handler(url, init));
  }));
}

describe("agent chat shell", () => {
  it("renders the shell and the composer", async () => {
    stubFetch(() => new Response(JSON.stringify(CONFIG), { status: 200 }));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();
    expect(container?.textContent).toContain("TS 团队知识 Agent");
    expect(container?.querySelector("textarea")).not.toBeNull();
    expect(container?.textContent).toContain("发送");
  });

  it("streams tool activity into one collapsed process block and renders markdown answer", async () => {
    stubFetch((url) => {
      if (url.includes("/api/v1/chat/stream")) return sseResponse(STREAM);
      return new Response(JSON.stringify(CONFIG), { status: 200 });
    });
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    const textarea = container?.querySelector("textarea") as HTMLTextAreaElement;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(textarea, "团队移动端组件库的架构是怎样的？");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await flush();

    await act(async () => {
      (container?.querySelector(".composer button") as HTMLButtonElement).click();
    });
    await flush();
    await flush();

    const processBlocks = container?.querySelectorAll("details.process");
    expect(processBlocks?.length).toBe(1);
    expect(processBlocks?.[0].querySelectorAll(".process-steps li").length).toBe(2);
    expect(processBlocks?.[0].textContent).toContain("检索知识库");
    expect((processBlocks?.[0] as HTMLDetailsElement).open).toBe(false);

    const heading = container?.querySelector(".markdown-body h2");
    expect(heading?.textContent).toBe("结论");
    expect(container?.querySelector(".markdown-body strong")?.textContent).toBe("Monorepo");
    expect(container?.textContent).toContain("members/whm/a/a.md");
  });

  it("shows an error message when the stream fails", async () => {
    stubFetch((url) => {
      if (url.includes("/api/v1/chat/stream")) return new Response("boom", { status: 500 });
      return new Response(JSON.stringify(CONFIG), { status: 200 });
    });
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    await act(async () => {
      (container?.querySelector(".composer button") as HTMLButtonElement).click();
    });
    await flush();
    expect(container?.querySelectorAll(".message-error").length).toBe(0);

    const textarea = container?.querySelector("textarea") as HTMLTextAreaElement;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(textarea, "任意问题");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await flush();
    await act(async () => {
      (container?.querySelector(".composer button") as HTMLButtonElement).click();
    });
    await flush();
    await flush();
    expect(container?.querySelector(".message-error")).not.toBeNull();
  });

  it("loads and saves runtime settings", async () => {
    const calls: { method: string; body: unknown }[] = [];
    stubFetch((url, init) => {
      if (init?.method === "PUT") {
        calls.push({ method: "PUT", body: JSON.parse(String(init.body)) });
        return new Response(JSON.stringify({ ...CONFIG, model: "deepseek-v4-pro" }), { status: 200 });
      }
      return new Response(JSON.stringify(CONFIG), { status: 200 });
    });
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    await act(async () => {
      (container?.querySelector(".settings-button") as HTMLButtonElement).click();
    });
    await flush();
    const dialog = container?.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(container?.querySelector(".chat-panel")).not.toBeNull();
    expect(dialog?.textContent).toContain("运行配置");
    expect((container?.querySelector(".modal-body input") as HTMLInputElement).value).toBe("ts_proxy");

    const modelInput = container?.querySelectorAll(".modal-body input")[1] as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(modelInput, "deepseek-v4-pro");
      modelInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await flush();
    await act(async () => {
      (container?.querySelector(".save-button") as HTMLButtonElement).click();
    });
    await flush();
    expect(calls.length).toBe(1);
    expect((calls[0].body as { model: string }).model).toBe("deepseek-v4-pro");
  });

  it("closes the settings modal on Escape", async () => {
    stubFetch(() => new Response(JSON.stringify(CONFIG), { status: 200 }));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();
    await act(async () => {
      (container?.querySelector(".settings-button") as HTMLButtonElement).click();
    });
    await flush();
    expect(container?.querySelector('[role="dialog"]')).not.toBeNull();
    await act(async () => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    await flush();
    expect(container?.querySelector('[role="dialog"]')).toBeNull();
  });
});
