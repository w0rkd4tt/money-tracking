"use client";

import { Fingerprint, KeyRound, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import {
  browserSupportsWebAuthn,
  platformAuthenticatorIsAvailable,
  startRegistration,
} from "@simplewebauthn/browser";

type Passkey = {
  id: number;
  name: string;
  transports: string | null;
  created_at: string;
  last_used_at: string | null;
};

async function jfetch<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
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

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("vi-VN");
  } catch {
    return iso;
  }
}

export function PasskeyPanel() {
  const [items, setItems] = useState<Passkey[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);
  const [platformAvail, setPlatformAvail] = useState<boolean | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const rows = await jfetch<Passkey[]>("/api/v1/ui/passkey");
      setItems(rows);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setSupported(browserSupportsWebAuthn());
    platformAuthenticatorIsAvailable()
      .then(setPlatformAvail)
      .catch(() => setPlatformAvail(false));
    refresh();
  }, []);

  async function enrol() {
    setErr(null);
    const defaultName =
      // Coarse guess so the user doesn't have to type for the common case.
      navigator.platform ||
      (navigator.userAgent.includes("Mac") ? "Mac" : "Thiết bị này");
    const name = window.prompt("Tên gợi nhớ cho passkey này:", defaultName);
    if (name == null) return; // cancelled
    setBusy(true);
    try {
      const begin = await jfetch<{
        state_id: string;
        options: unknown;
      }>("/api/v1/ui/passkey/register/begin", { method: "POST" });

      // Browser prompts for biometric / security key here.
      const credential = await startRegistration({
        optionsJSON: begin.options as Parameters<typeof startRegistration>[0]["optionsJSON"],
      });

      await jfetch("/api/v1/ui/passkey/register/finish", {
        json: {
          state_id: begin.state_id,
          response: credential,
          name: name.trim() || "Passkey",
        },
      });
      await refresh();
    } catch (e) {
      // User cancelling Touch ID throws DOMException("NotAllowedError").
      // We don't treat that as a loud error — just reset busy state.
      if (e instanceof Error && e.name === "NotAllowedError") {
        setErr("Đã huỷ đăng ký passkey");
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number, name: string) {
    if (!window.confirm(`Xoá passkey "${name}"?`)) return;
    setBusy(true);
    setErr(null);
    try {
      await jfetch(`/api/v1/ui/passkey/${id}`, { method: "DELETE" });
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold flex items-center gap-2">
          <Fingerprint size={18} /> Passkey (sinh trắc học)
        </h2>
        <button
          onClick={enrol}
          disabled={busy || !supported}
          className="btn btn-grd-primary text-sm"
          title={
            !supported
              ? "Trình duyệt không hỗ trợ WebAuthn"
              : "Đăng ký Touch ID / Face ID / Windows Hello / security key"
          }
        >
          {busy ? "…" : "+ Thêm passkey"}
        </button>
      </div>
      <p className="muted text-xs mt-2">
        Passkey dùng khoá public-key lưu trong Keychain / TPM — an toàn hơn PIN
        (không brute-force được). Mở khoá sẽ quét sinh trắc học thay vì nhập PIN.
      </p>
      {!supported && (
        <p className="neg text-xs mt-2">
          Trình duyệt hiện tại không hỗ trợ WebAuthn — dùng PIN.
        </p>
      )}
      {supported && platformAvail === false && (
        <p className="text-xs mt-2 text-amber-400">
          Thiết bị này không có platform authenticator (Touch ID / Windows
          Hello). Có thể dùng security key USB.
        </p>
      )}
      {err && <div className="neg text-sm mt-2">{err}</div>}

      <div className="mt-3 flex flex-col gap-2">
        {loading && <div className="muted text-sm">Đang tải…</div>}
        {!loading && items.length === 0 && (
          <div className="muted text-sm">Chưa đăng ký passkey nào.</div>
        )}
        {items.map((pk) => (
          <div
            key={pk.id}
            className="flex items-center justify-between gap-3 border border-[var(--border)] rounded px-3 py-2"
          >
            <div className="min-w-0 flex items-center gap-3">
              <KeyRound size={16} className="shrink-0 text-[var(--primary)]" />
              <div className="min-w-0">
                <div className="font-medium truncate">{pk.name}</div>
                <div className="muted text-xs">
                  {pk.transports || "—"} · thêm {fmtDate(pk.created_at)}
                  {pk.last_used_at && ` · dùng lần cuối ${fmtDate(pk.last_used_at)}`}
                </div>
              </div>
            </div>
            <button
              onClick={() => remove(pk.id, pk.name)}
              disabled={busy}
              className="p-1.5 rounded hover:bg-red-500/10 text-[var(--muted)] hover:text-[var(--danger)] disabled:opacity-50"
              title="Xoá"
            >
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
