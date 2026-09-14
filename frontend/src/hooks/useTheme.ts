import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "ts-kb-theme";

/** 读取首屏由 index.html 引导脚本设定的主题；缺省为 dark。 */
function initialTheme(): Theme {
  if (typeof document !== "undefined" && document.documentElement.dataset.theme === "light") {
    return "light";
  }
  return "dark";
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // 隐私模式下写入失败不影响本次会话
    }
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggle };
}
