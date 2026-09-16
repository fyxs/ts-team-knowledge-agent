import { afterEach, describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MarkdownView } from "./components/MarkdownView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const DOC_PATH = "members/whm/projects/kb-web/批量上传技术方案/批量上传技术方案.md";

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function render(content: string, basePath?: string) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root?.render(<MarkdownView content={content} basePath={basePath} />);
  });
  return container;
}

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
});

describe("document images", () => {
  it("rewrites a relative image to the knowledge asset route", () => {
    const node = render("![架构图](images/abc.jpg)", DOC_PATH);

    const image = node.querySelector("img.content-img") as HTMLImageElement | null;
    expect(image).not.toBeNull();
    expect(image?.getAttribute("src")).toContain("/api/v1/knowledge/asset?");
    expect(decodeURIComponent(image?.getAttribute("src") ?? "")).toContain(
      "members/whm/projects/kb-web/批量上传技术方案/images/abc.jpg",
    );
    expect(image?.getAttribute("alt")).toBe("架构图");
  });

  it("marks an author-local path as unavailable instead of rendering a broken image", () => {
    const node = render("![截图](C:\\Users\\du\\AppData\\Roaming\\Typora\\typora-user-images\\shot.png)", DOC_PATH);

    expect(node.querySelector("img")).toBeNull();
    expect(node.querySelector(".image-missing")?.textContent).toContain("图片不可用");
  });

  it("links an external image instead of hotlinking it", () => {
    const node = render("![外链图](https://wdcdn.qpic.cn/MTY4ODg1_614818.png)", DOC_PATH);

    expect(node.querySelector("img")).toBeNull();
    const link = node.querySelector("a.image-external") as HTMLAnchorElement | null;
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("https://wdcdn.qpic.cn/MTY4ODg1_614818.png");
    expect(link?.getAttribute("rel")).toBe("noreferrer");
  });

  it("treats a relative image as unavailable when there is no document to resolve it against", () => {
    const node = render("![配图](images/abc.jpg)");

    expect(node.querySelector("img")).toBeNull();
    expect(node.querySelector(".image-missing")).not.toBeNull();
  });
});
