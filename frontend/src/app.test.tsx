import { afterEach, describe, expect, it } from "vitest";
import { createRoot, type Root } from "react-dom/client";
import App from "./main";

let container: HTMLDivElement | null = null;
let root: Root | null = null;

async function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  root.render(<App />);
  await new Promise((resolve) => setTimeout(resolve, 0));
  return container;
}

afterEach(() => {
  root?.unmount();
  container?.remove();
  container = null;
  root = null;
});

describe("agent chat shell", () => {
  it("renders the chat interface with composer and settings", async () => {
    const view = await render();
    expect(view.textContent).toContain("TS 团队知识 Agent");
    expect(view.querySelector("textarea")).not.toBeNull();
    expect(view.querySelector(".composer button")).not.toBeNull();
  });

  it("renders the greeting message from the assistant", async () => {
    const view = await render();
    expect(view.textContent).toContain("知识库");
    expect(view.querySelectorAll(".message").length).toBeGreaterThan(0);
  });

  it("exposes the settings panel toggle", async () => {
    const view = await render();
    const toggle = view.querySelector(".settings-button") as HTMLButtonElement | null;
    expect(toggle).not.toBeNull();
    expect(view.querySelector(".settings-panel")).toBeNull();
    toggle?.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(view.querySelector(".settings-panel")).not.toBeNull();
    expect(view.textContent).toContain("Top-K");
  });
});
