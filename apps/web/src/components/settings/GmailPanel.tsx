"use client";

import { useCallback, useEffect, useState } from "react";

type Status = {
  connected: boolean;
  account_email: string | null;
  scopes: string | null;
  expires_at: string | null;
  last_sync_at: string | null;
  last_history_id: string | null;
  can_mark_read: boolean;
};

type SyncResult = {
  ok: boolean;
  processed: number;
  ingested: number;
  skipped: number;
  errors: number;
  marked_read: number;
  llm_fallback_used: number;
  history_id: string | null;
  message: string;
};

export function GmailPanel() {
  const [status, setStatus] = useState<Status | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [lastResult, setLastResult] = useState<SyncResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/v1/gmail/status", { cache: "no-store" });
      setStatus(await r.json());
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const connect = () => {
    window.location.href = "/api/v1/oauth/google/start";
  };

  const disconnect = async () => {
    if (!confirm("Ngắt kết nối Gmail? Dữ liệu đã ingest giữ nguyên, dừng đọc email mới.")) return;
    const r = await fetch("/api/v1/oauth/google", { method: "DELETE" });
    if (r.ok) {
      setLastResult(null);
      await load();
    }
  };

  const sync = async () => {
    setSyncing(true);
    setErr(null);
    try {
      const r = await fetch("/api/v1/gmail/sync", { method: "POST" });
      const data: SyncResult = await r.json();
      setLastResult(data);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="card space-y-3">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="font-semibold">📧 Gmail auto-ingest</h2>
          <p className="muted text-sm">
            Đọc email giao dịch (readonly) từ ngân hàng / ví → tạo transaction pending.
          </p>
        </div>
        {status?.connected ? (
          <div className="flex gap-2">
            <button
              onClick={sync}
              disabled={syncing}
              className="bg-blue-700 hover:bg-blue-600 text-white text-sm px-3 py-1.5 rounded disabled:opacity-50"
            >
              {syncing ? "⏳ Đang sync..." : "↻ Sync now"}
            </button>
            <button
              onClick={disconnect}
              className="bg-[var(--border)] hover:bg-red-900 text-sm px-3 py-1.5 rounded"
            >
              Ngắt kết nối
            </button>
          </div>
        ) : (
          <button
            onClick={connect}
            className="bg-blue-700 hover:bg-blue-600 text-white text-sm px-3 py-1.5 rounded"
          >
            Kết nối Gmail
          </button>
        )}
      </div>

      {err && <p className="text-red-400 text-sm">{err}</p>}

      {status?.connected && !status.can_mark_read && (
        <div className="border border-yellow-700/60 bg-yellow-900/20 rounded p-3 text-sm">
          <p className="font-semibold text-yellow-200">
            ⚠️ Scope cũ (readonly) — chưa mark-read được
          </p>
          <p className="muted mt-1">
            Gmail đã kết nối với scope <code>gmail.readonly</code>, chỉ đọc được
            email nhưng không thể đánh dấu đã đọc. Cần{" "}
            <b>ngắt kết nối & kết nối lại</b> để grant scope{" "}
            <code>gmail.modify</code>.
          </p>
          <div className="flex gap-2 mt-2">
            <button
              onClick={disconnect}
              className="bg-red-900 hover:bg-red-800 text-white text-xs px-3 py-1.5 rounded"
            >
              Ngắt kết nối
            </button>
            <button
              onClick={connect}
              className="bg-blue-700 hover:bg-blue-600 text-white text-xs px-3 py-1.5 rounded"
            >
              Kết nối lại (grant mark-read)
            </button>
          </div>
        </div>
      )}

      <table className="text-sm w-full">
        <tbody>
          <tr className="border-b border-[var(--border)]">
            <td className="py-1 muted w-40">Trạng thái</td>
            <td>
              {status === null
                ? "…"
                : status.connected
                ? (
                    <>
                      <span className="pos">✓ đã kết nối</span>
                      {status.account_email && (
                        <span className="ml-2 muted">({status.account_email})</span>
                      )}
                    </>
                  )
                : <span className="muted">chưa kết nối</span>}
            </td>
          </tr>
          <tr className="border-b border-[var(--border)]">
            <td className="py-1 muted">Scope</td>
            <td className="font-mono text-xs">{status?.scopes || "—"}</td>
          </tr>
          <tr className="border-b border-[var(--border)]">
            <td className="py-1 muted">Lần sync gần nhất</td>
            <td>
              {status?.last_sync_at
                ? new Date(status.last_sync_at + "Z").toLocaleString("vi-VN")
                : "chưa bao giờ"}
            </td>
          </tr>
          <tr>
            <td className="py-1 muted">historyId</td>
            <td className="font-mono text-xs">{status?.last_history_id || "—"}</td>
          </tr>
        </tbody>
      </table>

      {lastResult && (
        <div className="border-t border-[var(--border)] pt-3 text-sm">
          <div className="font-semibold mb-1">Kết quả sync vừa chạy</div>
          {lastResult.ok ? (
            <ul className="text-sm space-y-1">
              <li>
                Duyệt: <b>{lastResult.processed}</b> email · ingested{" "}
                <b className="pos">{lastResult.ingested}</b> · skipped{" "}
                <span className="muted">{lastResult.skipped}</span> · errors{" "}
                <span className={lastResult.errors ? "neg" : "muted"}>
                  {lastResult.errors}
                </span>
              </li>
              <li className="muted">
                đánh dấu đã đọc: <b>{lastResult.marked_read}</b> · LLM fallback{" "}
                <b>{lastResult.llm_fallback_used}</b>
              </li>
              {lastResult.history_id && (
                <li className="muted">new historyId: {lastResult.history_id}</li>
              )}
            </ul>
          ) : (
            <p className="neg">❌ {lastResult.message}</p>
          )}
        </div>
      )}

      {!status?.connected && (
        <details className="text-xs muted">
          <summary className="cursor-pointer hover:text-white">Cách setup OAuth</summary>
          <ol className="list-decimal pl-5 mt-2 space-y-1">
            <li>
              Google Cloud Console → tạo project mới (hoặc dùng có sẵn) →{" "}
              <b>Enable</b> Gmail API
            </li>
            <li>
              APIs &amp; Services → OAuth consent screen → <b>Testing</b> →
              thêm test user: <code>datnlqanalysts@gmail.com</code>
            </li>
            <li>
              Credentials → Create OAuth 2.0 Client ID → <b>Web application</b>.
              Authorized redirect URI:
              <pre className="bg-[var(--card)] rounded px-2 py-1 mt-1 text-[10px]">
                http://localhost:8000/api/v1/oauth/google/callback
              </pre>
            </li>
            <li>
              Copy Client ID + Secret vào <code>.env</code>:
              <pre className="bg-[var(--card)] rounded px-2 py-1 mt-1 text-[10px] whitespace-pre">
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
              </pre>
            </li>
            <li>
              <code>docker compose up -d --force-recreate api</code> rồi bấm
              "Kết nối Gmail".
            </li>
          </ol>
        </details>
      )}
    </div>
  );
}
