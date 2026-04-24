"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

async function fetchJSON<T>(
  path: string,
  init?: RequestInit & { json?: unknown }
): Promise<T> {
  const opts: RequestInit = { ...init };
  if (init?.json !== undefined) {
    opts.method = opts.method || "POST";
    opts.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    opts.body = JSON.stringify(init.json);
  }
  const r = await fetch(path, { cache: "no-store", ...opts });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export function UnlockForm() {
  const router = useRouter();
  const [p, setP] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await fetchJSON("/api/v1/ui/unlock", { json: { passphrase: p } });
      router.push("/");
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        <span className="muted">Mật khẩu</span>
        <input
          type="password"
          autoFocus
          className="field"
          value={p}
          onChange={(e) => setP(e.target.value)}
        />
      </label>
      {err && <div className="neg text-sm">{err}</div>}
      <button
        type="submit"
        disabled={busy || !p}
        className="btn btn-grd-primary justify-center py-2.5"
      >
        {busy ? "…" : "Mở khoá"}
      </button>
    </form>
  );
}
