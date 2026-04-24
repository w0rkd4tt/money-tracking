"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { markSession } from "@/lib/session-mark";
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

function keepDigits(s: string, max = 6) {
  return s.replace(/\D/g, "").slice(0, max);
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
    if (!/^\d{6}$/.test(p1)) {
      setErr("Mã PIN phải đúng 6 chữ số (0-9)");
      return;
    }
    if (p1 !== p2) {
      setErr("Xác nhận mã PIN không khớp");
      return;
    }
    setBusy(true);
    try {
      const res = await fetchJSON<{ recovery_key: string }>("/api/v1/ui/setup", {
        json: { pin: p1 },
      });
      markSession();
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
        <span className="muted">Mã PIN (6 chữ số)</span>
        <input
          type="password"
          autoFocus
          inputMode="numeric"
          pattern="[0-9]{6}"
          maxLength={6}
          autoComplete="new-password"
          className="field font-mono tracking-[0.4em] text-center text-lg"
          value={p1}
          onChange={(e) => setP1(keepDigits(e.target.value))}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="muted">Nhập lại mã PIN</span>
        <input
          type="password"
          inputMode="numeric"
          pattern="[0-9]{6}"
          maxLength={6}
          autoComplete="new-password"
          className="field font-mono tracking-[0.4em] text-center text-lg"
          value={p2}
          onChange={(e) => setP2(keepDigits(e.target.value))}
        />
      </label>
      {err && <div className="neg text-sm">{err}</div>}
      <button
        type="submit"
        disabled={busy || p1.length !== 6 || p2.length !== 6}
        className="btn btn-grd-primary justify-center py-2.5"
      >
        {busy ? "…" : "Tạo mã PIN"}
      </button>
    </form>
  );
}
