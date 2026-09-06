import { getInitData, isTelegram } from "./telegram";

const BASE = "/api";

let currentTeamId: number | null = null;

export function setTeamId(id: number | null): void {
  currentTeamId = id;
  try {
    if (id !== null) localStorage.setItem("teamId", String(id));
  } catch {
    // localStorage may be unavailable — fine, it's just a convenience cache
  }
}

export function getTeamId(): number | null {
  return currentTeamId;
}

function debugMemberId(): string | null {
  return new URLSearchParams(window.location.search).get("as");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");

  if (isTelegram()) {
    headers.set("X-Telegram-Init-Data", getInitData());
  } else {
    const id = debugMemberId();
    if (id) headers.set("X-Debug-Member-Id", id);
  }
  if (currentTeamId !== null) headers.set("X-Team-Id", String(currentTeamId));

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      // not JSON — fall back to raw text
    }
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
};
