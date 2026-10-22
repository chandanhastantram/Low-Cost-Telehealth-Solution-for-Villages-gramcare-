import { useCallback, useSyncExternalStore } from "react";

// Theme lives on <html data-theme>, set before paint by index.html. This hook
// just reads/flips it and keeps every toggle on the page in step.
const listeners = new Set();

function current() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("gc-theme", theme);
  } catch {
    /* private mode — theme just won't persist */
  }
  document.querySelector('meta[name="theme-color"]')?.setAttribute(
    "content",
    theme === "dark" ? "#121614" : "#1e6b47"
  );
  listeners.forEach((fn) => fn());
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, current);
  const toggle = useCallback(() => setTheme(theme === "dark" ? "light" : "dark"), [theme]);
  return { theme, toggle };
}
