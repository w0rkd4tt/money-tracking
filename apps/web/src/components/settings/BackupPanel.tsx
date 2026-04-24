"use client";

import { useCallback, useEffect, useState } from "react";

type BackupFile = {
  name: string;
  path: string;
  size_bytes: number;
  created_at: string;
};

async function jfetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { cache: "no-store", ...init });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function BackupPanel() {
  const [backups, setBackups] = useState<BackupFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await jfetch<BackupFile[]>("/api/v1/admin/backups");
      setBackups(list);
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const createBackup = async () => {
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      const b = await jfetch<BackupFile>("/api/v1/admin/backup", { method: "POST" });
      setMsg(`✓ Đã tạo ${b.name} (${fmtSize(b.size_bytes)})`);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const prune = async () => {
    if (!confirm("Xoá các backup cũ hơn retention_days?")) return;
    try {
      const r = await jfetch<{ removed: number }>("/api/v1/admin/backups/prune", {
        method: "POST",
      });
      setMsg(`✓ Pruned ${r.removed} file`);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const totalBytes = backups.reduce((s, b) => s + b.size_bytes, 0);

  return (
    <div className="card space-y-3">
      <div className="flex justify-between items-start flex-wrap gap-2">
        <div>
          <h2 className="font-semibold">💾 Database backup</h2>
          <p className="muted text-sm">
            Dump Postgres ra <code>./backups/</code> (repo root). Scheduler tự
            chạy daily lúc 02:00.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={createBackup}
            disabled={busy}
            className="bg-blue-700 hover:bg-blue-600 text-white text-sm px-3 py-1.5 rounded disabled:opacity-50"
          >
            {busy ? "⏳ đang dump..." : "+ Backup ngay"}
          </button>
          <button
            onClick={prune}
            className="bg-[var(--border)] hover:bg-red-900 text-sm px-3 py-1.5 rounded"
          >
            Prune
          </button>
          <button
            onClick={load}
            className="bg-[var(--border)] hover:bg-gray-700 text-sm px-3 py-1.5 rounded"
          >
            ↻
          </button>
        </div>
      </div>

      {msg && <p className="text-green-400 text-sm">{msg}</p>}
      {err && <p className="text-red-400 text-sm">{err}</p>}

      <div className="flex gap-4 text-sm muted">
        <span>
          {backups.length} file · {fmtSize(totalBytes)}
        </span>
      </div>

      {backups.length === 0 ? (
        <p className="muted text-sm">Chưa có backup nào. Click "Backup ngay" để bắt đầu.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="muted text-left">
              <th className="pb-2">File</th>
              <th>Thời gian</th>
              <th className="text-right">Kích thước</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {backups.map((b) => (
              <tr key={b.name} className="border-t border-[var(--border)]">
                <td className="py-2 font-mono text-xs">{b.name}</td>
                <td>{new Date(b.created_at).toLocaleString("vi-VN")}</td>
                <td className="text-right">{fmtSize(b.size_bytes)}</td>
                <td>
                  <a
                    href={`/api/v1/admin/backups/${encodeURIComponent(b.name)}`}
                    download
                    className="text-blue-400 text-xs hover:underline"
                  >
                    ⬇ Tải
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
