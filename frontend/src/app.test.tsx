import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import App from "./App";
/** 会话接口的测试替身：默认 7 条历史会话，POST 时追加一条新会话。 */
const BASE_SESSIONS = [
  { id: "s-env", title: "前端编码规范里对环境变量有什么要求？", updatedAt: Date.now() - 24 * 60_000 },
  { id: "s-components", title: "团队移动端组件库的架构是怎样的？", updatedAt: Date.now() - 3 * 60 * 60_000 },
  { id: "s-mineru", title: "MinerU 转换失败有哪些可重试的情况", updatedAt: Date.now() - 26 * 60 * 60_000 },
  { id: "s-repo", title: "共享知识仓的拉取与推送流程", updatedAt: Date.now() - 30 * 60 * 60_000 },
  { id: "s-scan", title: "扫描间隔与计划任务怎么配", updatedAt: Date.now() - 3 * 24 * 60 * 60_000 },
  { id: "s-citation", title: "引用来源为空是怎么回事", updatedAt: Date.now() - 4 * 24 * 60 * 60_000 },
  { id: "s-gate", title: "转换质量门禁的判定标准", updatedAt: Date.now() - 12 * 24 * 60 * 60_000 },
];

let testSessions = [...BASE_SESSIONS];
let createdSessions = 0;

// React 18 在测试环境需要显式声明，否则状态更新不会同步刷新。
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const CONFIG = {
  provider: "ts_proxy",
  model: "deepseek-v4-flash",
  base_url: "http://192.168.20.200:3000",
  max_tokens: 4096,
  max_steps: 8,
  scan_interval_minutes: 60,
  api_key: "configured (****klPQ)",
};

const RUN_STATUS = { running: false, started_at: null, last: null, report: null };

/** 默认路由：配置、运行状态；其余按用例覆写。 */
function defaultHandler(url: string, init?: RequestInit): Response {
  // 与后端一致：问答流结束时首条提问会成为会话标题，前端刷新列表后以服务端为准。
  if (url.includes("/api/v1/chat/stream")) {
    const body = init?.body ? (JSON.parse(String(init.body)) as { question?: string; session_id?: string }) : {};
    const session = testSessions.find((item) => item.id === body.session_id);
    if (session && session.title === "新会话" && body.question) {
      session.title = body.question.slice(0, 40);
    }
    return sseResponse([
      'data: {"type":"start","question":"q"}\n\n',
      'data: {"type":"answer","content":"好的","citations":[],"steps":1,"retrieved":true}\n\n',
    ]);
  }
  if (url.includes("/api/v1/sessions")) {
    if ((init?.method ?? "GET") === "POST") {
      createdSessions += 1;
      const session = { id: `s-created-${createdSessions}`, title: "新会话", updatedAt: Date.now() };
      testSessions = [session, ...testSessions];
      return new Response(JSON.stringify(session), { status: 200 });
    }
    const matched = url.match(/\/api\/v1\/sessions\/([^/]+)\/messages$/);
    if (matched) {
      const session = testSessions.find((item) => item.id === matched[1]) ?? null;
      return new Response(JSON.stringify({ session, messages: [] }), { status: 200 });
    }
    const byId = url.match(/\/api\/v1\/sessions\/([^/]+)$/);
    if (byId) {
      if ((init?.method ?? "GET") === "PATCH") {
        const body = init?.body ? (JSON.parse(String(init.body)) as { title?: string }) : {};
        const current = testSessions.find((item) => item.id === byId[1]);
        const updated = { id: byId[1], title: body.title ?? current?.title ?? "", updatedAt: Date.now() };
        testSessions = testSessions.map((item) => (item.id === byId[1] ? updated : item));
        return new Response(JSON.stringify(updated), { status: 200 });
      }
      if (init?.method === "DELETE") {
        testSessions = testSessions.filter((item) => item.id !== byId[1]);
        return new Response(JSON.stringify({ deleted: true, session_id: byId[1] }), { status: 200 });
      }
    }
    return new Response(JSON.stringify({ sessions: testSessions }), { status: 200 });
  }
  if (url.includes("/api/v1/run")) return new Response(JSON.stringify(RUN_STATUS), { status: 200 });
  if (url.includes("/api/v1/config")) return new Response(JSON.stringify(CONFIG), { status: 200 });
  return new Response("{}", { status: 200 });
}

const UNRETRIEVED_STREAM = [
  'data: {"type":"start","question":"q"}\n\n',
  'data: {"type":"answer","content":"我直接作答。","citations":[],"steps":1,"retrieved":false}\n\n',
];

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
  testSessions = [...BASE_SESSIONS];
  createdSessions = 0;
  localStorage.clear();
  document.documentElement.dataset.theme = "dark";
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
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();
    expect(container?.textContent).toContain("TS 团队知识 Agent");
    expect(container?.querySelector("textarea")).not.toBeNull();
    expect(container?.textContent).toContain("发送");
  });

  it("streams tool activity into one collapsed process block and renders markdown answer", async () => {
    stubFetch((url, init) => {
      if (url.includes("/api/v1/chat/stream")) return sseResponse(STREAM);
      return defaultHandler(url, init);
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
    stubFetch((url, init) => {
      if (url.includes("/api/v1/chat/stream")) return new Response("boom", { status: 500 });
      return defaultHandler(url, init);
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
      return defaultHandler(url, init);
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

    expect(container?.querySelector(".modal-footer .save-button")).not.toBeNull();
    const bodyText = container?.querySelector(".modal-body")?.textContent ?? "";
    expect(bodyText).toContain("API Key");

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

  it("defaults to dark and toggles to light with persistence", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(container?.querySelector(".theme-toggle")?.textContent).toBe("浅色");

    await act(async () => {
      (container?.querySelector(".theme-toggle") as HTMLButtonElement).click();
    });
    await flush();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("ts-kb-theme")).toBe("light");
    expect(container?.querySelector(".theme-toggle")?.textContent).toBe("深色");
  });

  it("triggers a scan from the settings modal and shows the run state", async () => {
    const posts: string[] = [];
    stubFetch((url, init) => {
      if (init?.method === "POST" && url.includes("/api/v1/run")) {
        posts.push(url);
        return new Response(JSON.stringify({ status: "started" }), { status: 200 });
      }
      return defaultHandler(url, init);
    });
    await act(async () => {
      root?.render(<App />);
    });
    await flush();
    await act(async () => {
      (container?.querySelector(".settings-button") as HTMLButtonElement).click();
    });
    await flush();

    const scanButton = Array.from(container?.querySelectorAll(".settings-actions button") ?? []).find(
      (button) => button.textContent === "立即扫描",
    ) as HTMLButtonElement;
    await act(async () => {
      scanButton.click();
    });
    await flush();
    expect(posts.length).toBe(1);
    expect(container?.textContent).toContain("已触发扫描");
  });

  it("pulls and pushes the shared knowledge repository", async () => {
    const calls: string[] = [];
    stubFetch((url, init) => {
      if (init?.method === "POST" && url.includes("/api/v1/repository/")) {
        calls.push(url);
        return new Response(JSON.stringify({ status: url.includes("pull") ? "pulled" : "pushed", commit: "abcdef123456", message: null }), { status: 200 });
      }
      return defaultHandler(url, init);
    });
    await act(async () => {
      root?.render(<App />);
    });
    await flush();
    await act(async () => {
      (container?.querySelector(".settings-button") as HTMLButtonElement).click();
    });
    await flush();

    const buttons = Array.from(container?.querySelectorAll(".settings-actions button") ?? []);
    const pullButton = buttons.find((button) => button.textContent === "拉取") as HTMLButtonElement;
    const pushButton = buttons.find((button) => button.textContent === "推送") as HTMLButtonElement;
    await act(async () => {
      pullButton.click();
    });
    await flush();
    await act(async () => {
      pushButton.click();
    });
    await flush();

    expect(calls.some((url) => url.includes("/api/v1/repository/pull"))).toBe(true);
    expect(calls.some((url) => url.includes("/api/v1/repository/push"))).toBe(true);

    // 同步结果就近显示在「共享知识仓」分区内，而不是弹窗底部
    const sections = Array.from(container?.querySelectorAll(".modal-body .settings-section") ?? []);
    const repoSections = sections.filter((section) => section.textContent?.includes("共享知识仓"));
    expect(repoSections.length).toBe(1);
    expect(repoSections[0].textContent).toContain("推送结果：pushed");
  });

  it("warns when an answer was produced without retrieval", async () => {
    stubFetch((url, init) => {
      if (url.includes("/api/v1/chat/stream")) return sseResponse(UNRETRIEVED_STREAM);
      return defaultHandler(url, init);
    });
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    const textarea = container?.querySelector("textarea") as HTMLTextAreaElement;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(textarea, "随便问问");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await flush();
    await act(async () => {
      (container?.querySelector(".composer button") as HTMLButtonElement).click();
    });
    await flush();
    await flush();

    expect(container?.querySelector(".unretrieved-note")?.textContent).toContain("未检索知识库");
  });

  it("closes the settings modal on Escape", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
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

  it("renders the session panel from the sessions API", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    expect(container?.querySelector(".session-panel")).not.toBeNull();
    expect(container?.querySelector(".session-head-title")?.textContent).toBe("历史会话");
    expect(container?.querySelectorAll(".session-item").length).toBe(BASE_SESSIONS.length);
    expect(container?.querySelector(".session-item[aria-current='true']")?.textContent).toContain(
      BASE_SESSIONS[0].title,
    );
    // 最近活动的会话落在「今天」分组
    expect(container?.querySelector(".session-group")?.textContent).toBe("今天");
    // 会话内容接口尚未实现，选中会话从空状态开始
    expect(container?.textContent).toContain("向团队知识库提问");
  });

  it("filters the session list by keyword", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    const search = container?.querySelector(".session-search input") as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(search, "MinerU");
      search.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await flush();

    expect(container?.querySelectorAll(".session-item").length).toBe(1);
    expect(container?.querySelector(".session-item")?.textContent).toContain("MinerU");
  });

  it("keeps each session's conversation separate", async () => {
    stubFetch((url, init) => {
      if (url.includes("/api/v1/chat/stream")) return sseResponse(UNRETRIEVED_STREAM);
      return defaultHandler(url, init);
    });
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    const ask = async (question: string) => {
      const textarea = container?.querySelector("textarea") as HTMLTextAreaElement;
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
      await act(async () => {
        setter?.call(textarea, question);
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await flush();
      await act(async () => {
        (container?.querySelector(".composer button") as HTMLButtonElement).click();
      });
      await flush();
      await flush();
    };

    await ask("第一条会话的问题");
    expect(container?.textContent).toContain("第一条会话的问题");

    const idle = Array.from(container?.querySelectorAll<HTMLButtonElement>(".session-item") ?? []).find(
      (item) => item.getAttribute("aria-current") === "false",
    );
    await act(async () => {
      idle?.click();
    });
    await flush();

    // 换到没有消息的会话：消息区回到空状态，上一条会话的内容不再出现
    expect(container?.textContent).not.toContain("第一条会话的问题");
    expect(container?.textContent).toContain("向团队知识库提问");

    // 切回原会话：提问仍在
    const back = Array.from(container?.querySelectorAll<HTMLButtonElement>(".session-item") ?? []).find(
      (item) => item.textContent?.includes(BASE_SESSIONS[0].title),
    );
    await act(async () => {
      back?.click();
    });
    await flush();
    expect(container?.textContent).toContain("第一条会话的问题");
  });

  it("creates a session and titles it from the first question", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    await act(async () => {
      (container?.querySelector(".session-new") as HTMLButtonElement).click();
    });
    await flush();

    const activeItem = () => container?.querySelector(".session-item[aria-current='true']");
    expect(container?.querySelectorAll(".session-item").length).toBe(BASE_SESSIONS.length + 1);
    expect(activeItem()?.textContent).toContain("新会话");
    expect(container?.textContent).toContain("向团队知识库提问");

    const textarea = container?.querySelector("textarea") as HTMLTextAreaElement;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(textarea, "环境变量怎么读");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await flush();
    await act(async () => {
      (container?.querySelector(".composer button") as HTMLButtonElement).click();
    });
    await flush();
    await flush();

    // 占位标题被首个问题替换
    expect(activeItem()?.textContent).toContain("环境变量怎么读");
  });

  it("collapses the session column into a floating dock and expands it back", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    const shell = () => container?.querySelector(".app-shell");
    expect(shell()?.classList.contains("is-collapsed")).toBe(false);
    expect(container?.querySelector(".session-dock")).toBeNull();

    // 面板头部的「折叠」：收起后浮出按钮组
    await act(async () => {
      (container?.querySelector(".session-collapse") as HTMLButtonElement).click();
    });
    await flush();
    expect(shell()?.classList.contains("is-collapsed")).toBe(true);
    const dockButtons = container?.querySelectorAll(".dock-button") ?? [];
    expect(dockButtons.length).toBe(2);
    expect(dockButtons[1].getAttribute("aria-label")).toBe("新建对话");

    // 悬浮组的「打开历史面板」：展回去，按钮组撤走
    await act(async () => {
      (dockButtons[0] as HTMLButtonElement).click();
    });
    await flush();
    expect(shell()?.classList.contains("is-collapsed")).toBe(false);
    expect(container?.querySelector(".session-dock")).toBeNull();
  });

  it("creates a session from the dock without reopening the panel", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();
    await act(async () => {
      (container?.querySelector(".session-collapse") as HTMLButtonElement).click();
    });
    await flush();

    const before = container?.querySelectorAll(".session-item").length ?? 0;
    await act(async () => {
      (container?.querySelectorAll(".dock-button")[1] as HTMLButtonElement).click();
    });
    await flush();

    expect(container?.querySelectorAll(".session-item").length).toBe(before + 1);
    // 快捷新建不该把用户刚收起来的面板又弹开
    expect(container?.querySelector(".app-shell")?.classList.contains("is-collapsed")).toBe(true);
  });

  it("renames a session inline: the menu opens the editor, the input takes focus, blur saves", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    const row = container?.querySelectorAll(".session-row")[0] as HTMLElement;
    await act(async () => {
      (row.querySelector(".session-action") as HTMLButtonElement).click();
    });
    await flush();
    await act(async () => {
      (row.querySelector(".session-menu-item") as HTMLButtonElement).click();
    });
    await flush();

    const input = container?.querySelector(".session-edit-input") as HTMLInputElement;
    expect(input).not.toBeNull();
    // 进入编辑即自动聚焦，不需要再点一下输入框
    expect(document.activeElement).toBe(input);

    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(input, "换个更短的名字");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await flush();

    await act(async () => {
      input.blur();
    });
    await flush();

    expect(testSessions.find((session) => session.id === "s-env")?.title).toBe("换个更短的名字");
    expect(container?.querySelector(".session-edit-input")).toBeNull();
  });

  it("falls back to the original title when the editor is emptied and blurred", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    const row = container?.querySelectorAll(".session-row")[0] as HTMLElement;
    await act(async () => {
      (row.querySelector(".session-action") as HTMLButtonElement).click();
    });
    await flush();
    await act(async () => {
      (row.querySelector(".session-menu-item") as HTMLButtonElement).click();
    });
    await flush();

    const input = container?.querySelector(".session-edit-input") as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(input, "   ");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      input.blur();
    });
    await flush();

    // 空标题没有意义：静默回退原名，不把空行留在列表里
    expect(testSessions.find((session) => session.id === "s-env")?.title).toBe("前端编码规范里对环境变量有什么要求？");
    expect(container?.querySelector(".session-edit-input")).toBeNull();
  });

  it("deletes a session through the confirm dialog", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    const before = container?.querySelectorAll(".session-item").length ?? 0;
    const row = container?.querySelectorAll(".session-row")[0] as HTMLElement;
    await act(async () => {
      (row.querySelector(".session-action") as HTMLButtonElement).click();
    });
    await flush();
    await act(async () => {
      (row.querySelector(".session-menu-item.is-danger") as HTMLButtonElement).click();
    });
    await flush();

    // 先弹确认框，并且点名删的是哪一条
    expect(container?.querySelector(".modal-panel.is-confirm")).not.toBeNull();
    expect(container?.querySelector(".confirm-text")?.textContent).toContain("前端编码规范里对环境变量有什么要求？");

    await act(async () => {
      (container?.querySelector(".confirm-delete") as HTMLButtonElement).click();
    });
    await flush();

    expect(container?.querySelectorAll(".session-item").length).toBe(before - 1);
    expect(testSessions.some((session) => session.id === "s-env")).toBe(false);
    expect(container?.querySelector(".modal-panel.is-confirm")).toBeNull();
  });

  it("creates a replacement session after deleting the last one", async () => {
    testSessions = [BASE_SESSIONS[0]];
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    const row = container?.querySelectorAll(".session-row")[0] as HTMLElement;
    await act(async () => {
      (row.querySelector(".session-action") as HTMLButtonElement).click();
    });
    await flush();
    const deleteItem = Array.from(row.querySelectorAll<HTMLButtonElement>(".session-menu-item")).find((item) =>
      item.textContent?.includes("删除"),
    );
    await act(async () => {
      deleteItem?.click();
    });
    await flush();
    await act(async () => {
      (container?.querySelector(".confirm-delete") as HTMLButtonElement).click();
    });
    await flush();

    // 删光后立刻补一个空会话，避免后续提问在服务端每条各建一个会话
    expect(testSessions.length).toBe(1);
    expect(testSessions[0].id).not.toBe("s-env");
    expect(container?.querySelectorAll(".session-item").length).toBe(1);
  });

  it("opens one answer in the focus view and returns with the close button", async () => {
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    const textarea = container?.querySelector("textarea") as HTMLTextAreaElement;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(textarea, "前端编码规范里对环境变量有什么要求？");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await flush();
    await act(async () => {
      (container?.querySelector(".composer button") as HTMLButtonElement).click();
    });
    await flush();

    await act(async () => {
      (container?.querySelector(".message-open") as HTMLButtonElement).click();
    });
    await flush();

    const view = container?.querySelector(".focus-view");
    expect(view).not.toBeNull();
    // 头部显示的是问题本身，比只写「集中阅读」更能说明在看哪一段
    expect(view?.querySelector("h1")?.textContent).toBe("前端编码规范里对环境变量有什么要求？");
    // 只呈现这一条答案，且视图内不再出现「全屏」入口——已经在里面了
    expect(view?.querySelectorAll(".message-assistant").length).toBe(1);
    expect(view?.querySelector(".message-open")).toBeNull();
    // 集中阅读是读的地方，不带输入区
    expect(view?.querySelector(".composer")).toBeNull();

    await act(async () => {
      (view?.querySelector(".focus-close") as HTMLButtonElement).click();
    });
    await flush();
    expect(container?.querySelector(".focus-view")).toBeNull();
  });

  it("keeps the active session in the URL so a refresh or a shared link returns to it", async () => {
    window.history.replaceState({}, "", "/");
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    expect(window.location.search).toContain(`session=${BASE_SESSIONS[0].id}`);

    const other = Array.from(container?.querySelectorAll<HTMLButtonElement>(".session-item") ?? []).find((item) =>
      item.textContent?.includes(BASE_SESSIONS[1].title),
    );
    await act(async () => {
      other?.click();
    });
    await flush();

    expect(window.location.search).toContain(`session=${BASE_SESSIONS[1].id}`);
    expect(container?.querySelector('.session-item[aria-current="true"]')?.textContent).toContain(BASE_SESSIONS[1].title);
    window.history.replaceState({}, "", "/");
  });

  it("restores the session written in the URL on load", async () => {
    window.history.replaceState({}, "", `/?session=${BASE_SESSIONS[2].id}`);
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    expect(container?.querySelector('.session-item[aria-current="true"]')?.textContent).toContain(BASE_SESSIONS[2].title);
    window.history.replaceState({}, "", "/");
  });

  it("falls back to the newest session when the URL points to a missing one", async () => {
    window.history.replaceState({}, "", "/?session=s-removed");
    stubFetch((url, init) => defaultHandler(url, init));
    await act(async () => {
      root?.render(<App />);
    });
    await flush();

    // 分享链接里的会话已被删除：回落到最近一条，并把地址栏纠正过来
    expect(container?.querySelector('.session-item[aria-current="true"]')?.textContent).toContain(BASE_SESSIONS[0].title);
    expect(window.location.search).toContain(`session=${BASE_SESSIONS[0].id}`);
    window.history.replaceState({}, "", "/");
  });
});
