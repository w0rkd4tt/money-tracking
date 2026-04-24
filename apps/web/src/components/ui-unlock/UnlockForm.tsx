"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { markSession } from "@/lib/session-mark";

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

export function UnlockForm() {
  const router = useRouter();
  const [p, setP] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Guard so auto-submit on 6th digit doesn't fire twice if the user edits
  // after a failed attempt (the error clears on change, but we already tried).
  const submittingRef = useRef(false);

  async function doSubmit(pin: string) {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setBusy(true);
    setErr(null);
    try {
      await fetchJSON("/api/v1/ui/unlock", { json: { pin } });
      markSession();
      router.push("/");
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setP("");
    } finally {
      setBusy(false);
      submittingRef.current = false;
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (p.length === 6) await doSubmit(p);
  }

  function onChange(next: string) {
    const digits = keepDigits(next);
    setP(digits);
    if (err) setErr(null);
    if (digits.length === 6 && !busy) {
      // Fire-and-forget: auto-submit as soon as the 6th digit lands so the
      // user doesn't need to also press Enter / tap a button.
      void doSubmit(digits);
    }
  }

  return (
    <form onSubmit={onSubmit} className="card flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        <span className="muted">Mã PIN</span>
        <input
          type="password"
          autoFocus
          inputMode="numeric"
          pattern="[0-9]{6}"
          maxLength={6}
          autoComplete="current-password"
          className="field font-mono tracking-[0.4em] text-center text-lg"
          value={p}
          onChange={(e) => onChange(e.target.value)}
          disabled={busy}
        />
      </label>
      {err && <div className="neg text-sm">{err}</div>}
      <button
        type="submit"
        disabled={busy || p.length !== 6}
        className="btn btn-grd-primary justify-center py-2.5"
      >
        {busy ? "…" : "Mở khoá"}
      </button>
    </form>
  );
}
