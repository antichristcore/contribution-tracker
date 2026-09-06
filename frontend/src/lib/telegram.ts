// Deliberately does NOT use @twa-dev/sdk's cached `WebApp` singleton: it
// captures window.Telegram.WebApp once at module import time, but Telegram
// (tdesktop at least) replaces that object with a fresh one once it finishes
// the native bridge handshake — the cached reference is left pointing at a
// stale object whose initData never fills in. Read window.Telegram.WebApp
// fresh on every call instead.

function webApp() {
  return window.Telegram?.WebApp;
}

export function isTelegram(): boolean {
  return Boolean(webApp()?.initData);
}

function applyThemeVars(): void {
  const app = webApp();
  if (!app) return;
  const root = document.documentElement;
  const params = (app.themeParams ?? {}) as Record<string, string | undefined>;
  const map: Record<string, string> = {
    bg_color: "--tg-bg-color",
    text_color: "--tg-text-color",
    hint_color: "--tg-hint-color",
    link_color: "--tg-link-color",
    button_color: "--tg-button-color",
    button_text_color: "--tg-button-text-color",
    secondary_bg_color: "--tg-secondary-bg-color",
    section_bg_color: "--tg-section-bg-color",
  };
  for (const [key, cssVar] of Object.entries(map)) {
    const value = params[key];
    if (value) root.style.setProperty(cssVar, value);
  }
  root.setAttribute("data-theme", app.colorScheme === "dark" ? "dark" : "light");
}

export function initTelegram(): void {
  const app = webApp();
  if (!app) return;
  try {
    app.ready?.();
    app.expand?.();
    applyThemeVars();
    app.onEvent?.("themeChanged", applyThemeVars);
  } catch {
    // not fatal if the bridge misbehaves in an unexpected client
  }
}

export function getInitData(): string {
  return webApp()?.initData ?? "";
}

export function openLink(url: string): void {
  // A plain window.open is blocked inside Telegram's webview — the client has
  // its own bridge for handing a URL to the system browser.
  const app = webApp();
  try {
    if (app?.openLink) {
      app.openLink(url);
      return;
    }
  } catch {
    // fall through to the browser behaviour below
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

type ImpactStyle = "light" | "medium" | "heavy" | "rigid" | "soft";

export function haptic(kind: ImpactStyle | "success" | "error" | "warning" = "light"): void {
  const app = webApp();
  if (!app) return;
  try {
    if (kind === "success" || kind === "error" || kind === "warning") {
      app.HapticFeedback?.notificationOccurred?.(kind);
    } else {
      app.HapticFeedback?.impactOccurred?.(kind);
    }
  } catch {
    // haptics are a nice-to-have
  }
}
