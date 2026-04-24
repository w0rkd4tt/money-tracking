"use client";

import { useMemo, useState } from "react";

type Account = {
  id: number;
  name: string;
  type: string;
  currency: string;
  archived: boolean;
  icon?: string | null;
};

type Category = {
  id: number;
  name: string;
  path: string;
  kind: "expense" | "income" | "transfer";
};

export type TxKind = "expense" | "income";

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

function parseAmount(raw: string): number | null {
  const cleaned = raw.replace(/[\s,._]/g, "").trim();
  if (!cleaned) return null;
  // Support shorthand: "50k" = 50_000, "1.2m" = 1_200_000
  const m = cleaned.match(/^(-?\d+(?:[.,]\d+)?)(k|m|tr|tỷ|ty)?$/i);
  if (!m) return null;
  const n = parseFloat(m[1].replace(",", "."));
  if (Number.isNaN(n)) return null;
  const suf = (m[2] || "").toLowerCase();
  const mult =
    suf === "k"
      ? 1_000
      : suf === "m" || suf === "tr"
        ? 1_000_000
        : suf === "tỷ" || suf === "ty"
          ? 1_000_000_000
          : 1;
  return n * mult;
}

type FormState = {
  kind: TxKind;
  ts: string;
  account_id: string;
  category_id: string;
  amount: string;
  merchant_text: string;
  note: string;
};

function emptyForm(defaultAccountId?: number): FormState {
  return {
    kind: "expense",
    ts: nowLocal(),
    account_id: defaultAccountId ? String(defaultAccountId) : "",
    category_id: "",
    amount: "",
    merchant_text: "",
    note: "",
  };
}

export function TransactionForm({
  accounts,
  categories,
  onCreated,
  onCancel,
  compact,
}: {
  accounts: Account[];
  categories: Category[];
  onCreated?: () => void | Promise<void>;
  onCancel?: () => void;
  compact?: boolean;
}) {
  const activeAccounts = useMemo(
    () => accounts.filter((a) => !a.archived),
    [accounts]
  );
  const defaultAccountId = activeAccounts[0]?.id;

  const [v, setV] = useState<FormState>(() => emptyForm(defaultAccountId));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const amountNum = parseAmount(v.amount);
  const validCats = categories.filter((c) => c.kind === v.kind);

  async function submit(resetAfter: boolean) {
    setErr(null);
    setOkMsg(null);
    if (!v.account_id) {
      setErr("Chọn tài khoản");
      return;
    }
    if (amountNum === null || amountNum <= 0) {
      setErr("Số tiền không hợp lệ (ví dụ: 45000 hoặc 45k)");
      return;
    }
    setBusy(true);
    try {
      const signed = v.kind === "expense" ? -Math.abs(amountNum) : Math.abs(amountNum);
      await fetchJSON("/api/v1/transactions", {
        json: {
          ts: new Date(v.ts).toISOString(),
          amount: String(signed),
          account_id: Number(v.account_id),
          category_id: v.category_id ? Number(v.category_id) : null,
          merchant_text: v.merchant_text.trim() || null,
          note: v.note.trim() || null,
          source: "manual",
          status: "confirmed",
        },
      });
      setOkMsg("✓ Đã lưu giao dịch");
      if (onCreated) await onCreated();
      if (resetAfter) {
        setV(emptyForm(defaultAccountId));
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={compact ? "flex flex-col gap-2" : "flex flex-col gap-3"}>
      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => setV({ ...v, kind: "expense", category_id: "" })}
          className={`text-sm px-3 py-1 rounded ${
            v.kind === "expense"
              ? "bg-red-700 text-white"
              : "border border-[var(--border)]"
          }`}
        >
          − Chi
        </button>
        <button
          type="button"
          onClick={() => setV({ ...v, kind: "income", category_id: "" })}
          className={`text-sm px-3 py-1 rounded ${
            v.kind === "income"
              ? "bg-emerald-700 text-white"
              : "border border-[var(--border)]"
          }`}
        >
          + Thu
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Số tiền</span>
          <input
            inputMode="decimal"
            className="field"
            value={v.amount}
            onChange={(e) => setV({ ...v, amount: e.target.value })}
            placeholder="45k, 1.2m, 500000…"
            autoFocus
          />
          {amountNum !== null && amountNum > 0 && (
            <span className="text-xs muted">
              = {new Intl.NumberFormat("vi-VN").format(Math.round(amountNum))} ₫
            </span>
          )}
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Thời gian</span>
          <input
            type="datetime-local"
            className="field"
            value={v.ts}
            onChange={(e) => setV({ ...v, ts: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Tài khoản</span>
          <select
            className="field"
            value={v.account_id}
            onChange={(e) => setV({ ...v, account_id: e.target.value })}
          >
            <option value="">— chọn —</option>
            {activeAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.icon ? `${a.icon} ` : ""}
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Danh mục</span>
          <select
            className="field"
            value={v.category_id}
            onChange={(e) => setV({ ...v, category_id: e.target.value })}
          >
            <option value="">— không phân loại —</option>
            {validCats.map((c) => (
              <option key={c.id} value={c.id}>
                {c.path || c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Merchant / nơi tiêu</span>
          <input
            className="field"
            value={v.merchant_text}
            onChange={(e) => setV({ ...v, merchant_text: e.target.value })}
            placeholder="VD: Highland Coffee"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Ghi chú</span>
          <input
            className="field"
            value={v.note}
            onChange={(e) => setV({ ...v, note: e.target.value })}
            placeholder="VD: ăn trưa với team"
          />
        </label>
      </div>

      {err && <div className="neg text-sm">{err}</div>}
      {okMsg && <div className="pos text-sm">{okMsg}</div>}

      <div className="flex gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => submit(false)}
          disabled={busy}
          className="btn btn-grd-primary"
        >
          {busy ? "…" : "Lưu"}
        </button>
        <button
          type="button"
          onClick={() => submit(true)}
          disabled={busy}
          className="btn btn-primary"
          title="Lưu và tiếp tục nhập giao dịch mới"
        >
          Lưu + Thêm nữa
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="btn btn-ghost">
            Đóng
          </button>
        )}
      </div>
    </div>
  );
}
