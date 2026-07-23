/**
 * Theme handling: dark, light, or follow the operating system.
 *
 * The choice is stored in localStorage and applied by toggling a `light`
 * class on <html>, which swaps the CSS custom properties in index.css.
 * "system" subscribes to the OS preference so the app follows it live.
 */
const KEY = "ecoreport_theme";
const mql = () => window.matchMedia("(prefers-color-scheme: light)");

export const getTheme = () => localStorage.getItem(KEY) || "dark";

export function applyTheme(theme = getTheme()) {
  const wantLight = theme === "light" || (theme === "system" && mql().matches);
  document.documentElement.classList.toggle("light", wantLight);
  document.documentElement.style.colorScheme = wantLight ? "light" : "dark";
}

export function setTheme(theme) {
  localStorage.setItem(KEY, theme);
  applyTheme(theme);
}

/** Keep "system" in step with the OS while the app is open. */
export function watchSystemTheme() {
  const handler = () => {
    if (getTheme() === "system") applyTheme("system");
  };
  const m = mql();
  m.addEventListener ? m.addEventListener("change", handler)
                     : m.addListener(handler);
  return () => {
    m.removeEventListener ? m.removeEventListener("change", handler)
                          : m.removeListener(handler);
  };
}
