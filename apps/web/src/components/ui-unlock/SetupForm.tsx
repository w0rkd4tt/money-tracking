"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { RecoveryKeyPanel } from "./RecoveryKeyPanel";

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

export function SetupForm() {
  const router = useRouter();
  const [p1, setP1] = useState("");
  const [p2, setP2] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (p1.length < 8) {
      setErr("Mật khẩu tối thiểu 8 ký tự");
      return;
    }
    if (p1 !== p2) {
      setErr("Xác nhận mật khẩu không khớp");
      return;
    }
    setBusy(true);
    try {
      const res = await fetchJSON<{ recovery_key: string }>("/api/v1/ui/setup", {
        json: { passphrase: p1 },
      });
      setRecovery(res.recovery_key);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (recovery) {
    return (
      <RecoveryKeyPanel
        recoveryKey={recovery}
        label="Khoá khôi phục mới"
        onContinue={() => {
          router.push("/");
          router.refresh();
        }}
      />
    );
  }

  return (
    <form onSubmit={submit} className="card flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        <span className="muted">Mật khẩu (≥ 8 ký tự)</span>
        <input
          type="password"
          autoFocus
          className="field"
          value={p1}
          onChange={(e) => setP1(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="muted">Nhập lại mật khẩu</span>
        <input
          type="password"
          className="field"
          value={p2}
          onChange={(e) => setP2(e.target.value)}
        />
      </label>
      {err && <div className="neg text-sm">{err}</div>}
      <button
        type="submit"
        disabled={busy}
        className="btn btn-grd-primary justify-center py-2.5"
      >
        {busy ? "…" : "Tạo mật khẩu"}
      </button>
    </form>
  );
}
