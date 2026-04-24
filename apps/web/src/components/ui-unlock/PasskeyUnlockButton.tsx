"use client";

import { Fingerprint } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  browserSupportsWebAuthn,
  startAuthentication,
} from "@simplewebauthn/browser";
import { markSession } from "@/lib/session-mark";

async function jfetch<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
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

/**
 * Triggers the WebAuthn authentication ceremony. Rendered above the PIN input
 * on /unlock only when the user has at least one passkey enrolled (via
 * status.passkey_count).
 *
 * With `autoTrigger`, fires the ceremony once on mount so Touch ID / Face ID
 * pops immediately — no click needed. If the user cancels (NotAllowedError)
 * we leave the button visible so they can retry manually; we don't re-fire
 * because the browser treats repeated programmatic prompts as abusive.
 */
export function PasskeyUnlockButton({ autoTrigger = false }: { autoTrigger?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const autoFiredRef = useRef(false);

  if (typeof window !== "undefined" && !browserSupportsWebAuthn()) {
    return null;
  }

  async function unlock(): Promise<boolean> {
    setErr(null);
    setBusy(true);
    try {
      const begin = await jfetch<{ state_id: string; options: unknown }>(
        "/api/v1/ui/passkey/auth/begin",
        { method: "POST" }
      );
      const assertion = await startAuthentication({
        optionsJSON: begin.options as Parameters<typeof startAuthentication>[0]["optionsJSON"],
      });
      await jfetch("/api/v1/ui/passkey/auth/finish", {
        json: { state_id: begin.state_id, response: assertion },
      });
      markSession();
      router.push("/");
      router.refresh();
      return true;
    } catch (e) {
      if (e instanceof Error && e.name === "NotAllowedError") {
        setErr("Đã huỷ — chạm để thử lại");
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
      return false;
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!autoTrigger) return;
    let cancelled = false;

    // Unconditional 5s delay before the Touch ID sheet pops — avoids noise
    // right after a lock hotkey and gives the user a chance to reach for
    // the PIN input or click away without a prompt interrupting. If they
    // really want the sheet immediately, the button below is still clickable
    // during the wait.
    const timer = window.setTimeout(async () => {
      if (cancelled || autoFiredRef.current || busy) return;
      autoFiredRef.current = true;
      const ok = await unlock();
      if (!ok) autoFiredRef.current = false;
    }, 5000);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoTrigger]);

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={unlock}
        disabled={busy}
        className="inline-flex items-center justify-center gap-2 border border-[var(--border)] hover:bg-[var(--border)]/40 rounded-lg py-2.5 text-sm font-medium disabled:opacity-60"
      >
        <Fingerprint size={18} />
        {busy ? "Đang xác thực…" : "Mở khoá bằng passkey (Touch ID / Face ID)"}
      </button>
      {err && <div className="neg text-xs text-center">{err}</div>}
    </div>
  );
}
