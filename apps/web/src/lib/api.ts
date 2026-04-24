export const API_BASE =
  (typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || "http://api:8000"
    : "") + "/api/v1";

async function getForwardCookieHeader(): Promise<string | null> {
  // Server-side: forward the browser's cookies so the API sees our `mt_session`
  // and can report `unlocked=true` to server components that call /ui/status.
  if (typeof window !== "undefined") return null;
  try {
    const { cookies } = await import("next/headers");
    const store = cookies();
    const all = store.getAll();
    if (!all.length) return null;
    return all.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch {
    return null;
  }
}

export async function api<T>(
  path: string,
  init?: RequestInit & { json?: unknown }
): Promise<T> {
  const opts: RequestInit = { cache: "no-store", ...init };
  const headers = new Headers(opts.headers || {});
  if (init?.json !== undefined) {
    opts.method = opts.method || "POST";
    headers.set("Content-Type", "application/json");
    opts.body = JSON.stringify(init.json);
  }
  const forward = await getForwardCookieHeader();
  if (forward) headers.set("Cookie", forward);
  opts.headers = headers;
  const r = await fetch(API_BASE + path, opts);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text()}`);
  return (await r.json()) as T;
}

export function fmtVND(n: number | string): string {
  const v = typeof n === "string" ? Number(n) : n;
  if (Number.isNaN(v)) return String(n);
  return new Intl.NumberFormat("vi-VN").format(Math.round(v)) + " ₫";
}

export function fmtDate(d: string): string {
  try {
    return new Date(d).toLocaleString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return d;
  }
}
