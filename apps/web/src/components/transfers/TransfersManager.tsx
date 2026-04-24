"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { fmtDate, fmtVND } from "@/lib/api";

type Account = {
  id: number;
  name: string;
  type: string;
  currency: string;
  icon: string | null;
  archived: boolean;
};

type Transfer = {
  id: number;
  ts: string;
  from_account_id: number;
  to_account_id: number;
  amount: string;
  fee: string;
  currency: string;
  fx_rate: string | null;
  note: string | null;
  source: string;
  transaction_ids: number[];
};

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

function nowLocal(): string {
  const d = new Date();
  d.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

type FormState = {
  ts: string;
  from_account_id: string;
  to_account_id: string;
  amount: string;
  fee: string;
  note: string;
};

const emptyForm = (): FormState => ({
  ts: nowLocal(),
  from_account_id: "",
  to_account_id: "",
  amount: "",
  fee: "0",
  note: "",
});

function TransferForm({
  accounts,
  onSubmit,
  onCancel,
  presetFrom,
  presetTo,
}: {
  accounts: Account[];
  onSubmit: (v: FormState) => Promise<void>;
  onCancel?: () => void;
  presetFrom?: string;
  presetTo?: string;
}) {
  const active = accounts.filter((a) => !a.archived);
  const [v, setV] = useState<FormState>(() => ({
    ...emptyForm(),
    from_account_id: presetFrom || (active[0]?.id ? String(active[0].id) : ""),
    to_account_id: presetTo || (active[1]?.id ? String(active[1].id) : ""),
  }));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const validate = (): string | null => {
    if (!v.from_account_id || !v.to_account_id) return "Chọn cả nguồn và đích";
    if (v.from_account_id === v.to_account_id)
      return "Nguồn và đích phải khác nhau";
    if (!v.amount || Number(v.amount) <= 0) return "Số tiền phải > 0";
    return null;
  };

  const save = async () => {
    const bad = validate();
    if (bad) {
      setErr(bad);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await onSubmit(v);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const quickPairs: { from: string; to: string; label: string }[] = [];
  const byType: Record<string, Account[]> = {};
  for (const a of active) byType[a.type] = (byType[a.type] || []).concat(a);
  const cash = byType["cash"] || [];
  const banks = byType["bank"] || [];
  const wallets = byType["ewallet"] || [];
  for (const b of banks) {
    for (const c of cash) {
      quickPairs.push({ from: String(b.id), to: String(c.id), label: `Rút ${b.name} → ${c.name}` });
      quickPairs.push({ from: String(c.id), to: String(b.id), label: `Nạp ${c.name} → ${b.name}` });
    }
  }
  for (const w of wallets) {
    for (const b of banks) {
      quickPairs.push({ from: String(b.id), to: String(w.id), label: `Nạp ${b.name} → ${w.name}` });
    }
  }

  return (
    <div className="space-y-3">
      {err && <div className="text-red-400 text-sm">{err}</div>}
      {quickPairs.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {quickPairs.slice(0, 8).map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => setV({ ...v, from_account_id: p.from, to_account_id: p.to })}
              className="text-xs bg-[var(--border)] hover:bg-blue-900 rounded-full px-3 py-1"
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
      <div className="grid md:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Từ (nguồn)</span>
          <select
            value={v.from_account_id}
            onChange={(e) => setV({ ...v, from_account_id: e.target.value })}
            className="field"
          >
            <option value="">—</option>
            {active.map((a) => (
              <option key={a.id} value={a.id}>
                {a.icon ?? ""} {a.name} ({a.type})
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Đến (đích)</span>
          <select
            value={v.to_account_id}
            onChange={(e) => setV({ ...v, to_account_id: e.target.value })}
            className="field"
          >
            <option value="">—</option>
            {active.map((a) => (
              <option key={a.id} value={a.id}>
                {a.icon ?? ""} {a.name} ({a.type})
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Số tiền</span>
          <input
            value={v.amount}
            onChange={(e) => setV({ ...v, amount: e.target.value })}
            inputMode="decimal"
            placeholder="VD: 500000"
            className="field"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Phí (mặc định 0)</span>
          <input
            value={v.fee}
            onChange={(e) => setV({ ...v, fee: e.target.value })}
            inputMode="decimal"
            className="field"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Ngày giờ</span>
          <input
            type="datetime-local"
            value={v.ts}
            onChange={(e) => setV({ ...v, ts: e.target.value })}
            className="field"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm md:col-span-2">
          <span className="muted">Ghi chú</span>
          <input
            value={v.note}
            onChange={(e) => setV({ ...v, note: e.target.value })}
            placeholder="VD: Rút ATM tại VCB chi nhánh X"
            className="field"
          />
        </label>
      </div>
      <div className="flex gap-2">
        <button
          onClick={save}
          disabled={busy}
          className="btn btn-grd-primary"
        >
          {busy ? "..." : "Tạo transfer"}
        </button>
        {onCancel && (
          <button
            onClick={onCancel}
            className="bg-[var(--border)] hover:bg-gray-700 text-sm px-4 py-1.5 rounded"
          >
            Huỷ
          </button>
        )}
      </div>
    </div>
  );
}

export function TransfersManager({
  initialAccounts,
  initialTransfers,
}: {
  initialAccounts: Account[];
  initialTransfers: Transfer[];
}) {
  const [accounts, setAccounts] = useState<Account[]>(initialAccounts);
  const [transfers, setTransfers] = useState<Transfer[]>(initialTransfers);
  const [creating, setCreating] = useState(true);

  const refresh = useCallback(async () => {
    const [a, t] = await Promise.all([
      fetchJSON<Account[]>("/api/v1/accounts"),
      fetchJSON<Transfer[]>("/api/v1/transfers"),
    ]);
    setAccounts(a);
    setTransfers(t);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const accMap = useMemo(
    () => Object.fromEntries(accounts.map((a) => [a.id, a])),
    [accounts]
  );

  const create = async (v: FormState) => {
    await fetchJSON("/api/v1/transfers", {
      json: {
        ts: v.ts,
        from_account_id: Number(v.from_account_id),
        to_account_id: Number(v.to_account_id),
        amount: v.amount,
        fee: v.fee || "0",
        note: v.note || null,
      },
    });
    await refresh();
  };

  const remove = async (t: Transfer) => {
    const fromA = accMap[t.from_account_id]?.name || t.from_account_id;
    const toA = accMap[t.to_account_id]?.name || t.to_account_id;
    if (!confirm(`Xoá transfer ${fmtVND(t.amount)} từ ${fromA} → ${toA}? Cả 2 giao dịch con cũng bị xoá.`)) return;
    await fetchJSON(`/api/v1/transfers/${t.id}`, { method: "DELETE" });
    await refresh();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">Transfers (rút / nạp / chuyển)</h1>
          <p className="muted text-sm">
            {transfers.length} transfer · không tính vào chi/thu
          </p>
        </div>
        <button
          onClick={() => setCreating((x) => !x)}
          className="btn btn-grd-primary"
        >
          {creating ? "✕ Đóng form" : "+ Transfer mới"}
        </button>
      </div>

      {creating && (
        <div className="card border-blue-700">
          <h2 className="font-semibold mb-3">Transfer mới</h2>
          <TransferForm accounts={accounts} onSubmit={create} />
        </div>
      )}

      <div className="card overflow-auto">
        {transfers.length === 0 ? (
          <p className="muted text-sm">Chưa có transfer nào.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="muted text-left border-b border-[var(--border)]">
                <th className="pb-2">Thời gian</th>
                <th>Từ</th>
                <th>Đến</th>
                <th className="text-right">Số tiền</th>
                <th className="text-right">Phí</th>
                <th>Ghi chú</th>
                <th>Nguồn</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {transfers.map((t) => {
                const fromA = accMap[t.from_account_id];
                const toA = accMap[t.to_account_id];
                return (
                  <tr key={t.id} className="border-b border-[var(--border)]">
                    <td className="py-2 whitespace-nowrap">{fmtDate(t.ts)}</td>
                    <td>
                      <span className="text-lg mr-1">{fromA?.icon ?? ""}</span>
                      {fromA?.name ?? t.from_account_id}
                    </td>
                    <td>
                      <span className="text-lg mr-1">{toA?.icon ?? ""}</span>
                      {toA?.name ?? t.to_account_id}
                    </td>
                    <td className="text-right font-mono">{fmtVND(t.amount)}</td>
                    <td className="text-right font-mono muted">{fmtVND(t.fee)}</td>
                    <td>{t.note || "—"}</td>
                    <td className="muted">{t.source}</td>
                    <td>
                      <button
                        onClick={() => remove(t)}
                        className="text-xs bg-red-900 hover:bg-red-800 text-white rounded px-2 py-1"
                        title="Xoá"
                      >
                        🗑
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
