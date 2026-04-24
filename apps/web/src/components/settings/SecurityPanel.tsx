"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { RecoveryKeyPanel } from "@/components/ui-unlock/RecoveryKeyPanel";

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
  if (r.status === 204) return undefined as T;
  return r.json();
}

function keepDigits(s: string, max = 6) {
  return s.replace(/\D/g, "").slice(0, max);
}

export function SecurityPanel() {
  const router = useRouter();
  const [show, setShow] = useState(false);
  const [oldP, setOldP] = useState("");
  const [newP, setNewP] = useState("");
  const [newP2, setNewP2] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [newRecovery, setNewRecovery] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!/^\d{6}$/.test(oldP)) {
      setErr("Mã PIN hiện tại phải là 6 chữ số");
      return;
    }
    if (!/^\d{6}$/.test(newP)) {
      setErr("Mã PIN mới phải là 6 chữ số");
      return;
    }
    if (newP !== newP2) {
      setErr("Xác nhận mã PIN không khớp");
      return;
    }
    setBusy(true);
    try {
      const res = await fetchJSON<{ new_recovery_key: string }>(
        "/api/v1/ui/change-pin",
        { json: { old_pin: oldP, new_pin: newP } }
      );
      setNewRecovery(res.new_recovery_key);
      setOldP("");
      setNewP("");
      setNewP2("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (newRecovery) {
    return (
      <section className="card">
        <h2 className="font-semibold mb-2">🔐 Bảo mật</h2>
        <RecoveryKeyPanel
          recoveryKey={newRecovery}
          label="Đã đổi mã PIN. Khoá khôi phục MỚI"
          onContinue={() => {
            setNewRecovery(null);
            setShow(false);
            router.refresh();
          }}
        />
      </section>
    );
  }

  return (
    <section className="card">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">🔐 Bảo mật</h2>
        <button
          onClick={() => setShow((s) => !s)}
          className="btn btn-ghost"
        >
          {show ? "Đóng" : "Đổi mã PIN"}
        </button>
      </div>
      {show && (
        <form onSubmit={submit} className="flex flex-col gap-2 mt-3">
          <p className="muted text-xs">
            Đổi mã PIN sẽ <strong>rotate khoá khôi phục</strong> và logout
            tất cả thiết bị khác. Khoá cũ sẽ không còn tác dụng.
          </p>
          <label className="flex flex-col gap-1 text-sm">
            <span className="muted">Mã PIN hiện tại</span>
            <input
              type="password"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              autoComplete="current-password"
              className="field font-mono tracking-[0.4em] text-center"
              value={oldP}
              onChange={(e) => setOldP(keepDigits(e.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="muted">Mã PIN mới (6 chữ số)</span>
            <input
              type="password"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              autoComplete="new-password"
              className="field font-mono tracking-[0.4em] text-center"
              value={newP}
              onChange={(e) => setNewP(keepDigits(e.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="muted">Nhập lại mã PIN mới</span>
            <input
              type="password"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              autoComplete="new-password"
              className="field font-mono tracking-[0.4em] text-center"
              value={newP2}
              onChange={(e) => setNewP2(keepDigits(e.target.value))}
            />
          </label>
          {err && <div className="neg text-sm">{err}</div>}
          <button
            type="submit"
            disabled={busy || oldP.length !== 6 || newP.length !== 6 || newP2.length !== 6}
            className="btn btn-grd-primary self-start"
          >
            {busy ? "…" : "Đổi mã PIN"}
          </button>
        </form>
      )}
    </section>
  );
}
