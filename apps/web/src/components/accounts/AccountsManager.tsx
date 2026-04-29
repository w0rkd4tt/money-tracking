"use client";

import { ArchiveRestore, Pencil, Plus, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fmtVND } from "@/lib/api";

type Account = {
  id: number;
  name: string;
  type: string;
  currency: string;
  opening_balance: string;
  icon: string | null;
  color: string | null;
  is_default: boolean;
  archived: boolean;
  credit_limit: string | null;
  statement_close_day: number | null;
};

type Balance = {
  account_id: number;
  balance: string;
  currency: string;
  credit_limit: string | null;
  debt: string | null;
  available_credit: string | null;
  utilization_pct: number | null;
};

const TYPES: { value: string; label: string; icon: string }[] = [
  { value: "cash", label: "Tiền mặt", icon: "💵" },
  { value: "bank", label: "Ngân hàng", icon: "🏦" },
  { value: "ewallet", label: "Ví điện tử", icon: "📱" },
  { value: "credit", label: "Thẻ tín dụng", icon: "💳" },
  { value: "saving", label: "Tiết kiệm", icon: "🏛️" },
  { value: "investment", label: "Đầu tư", icon: "📈" },
];

const COLORS = [
  "#6b7280",
  "#1d4ed8",
  "#059669",
  "#ec4899",
  "#f59e0b",
  "#8b5cf6",
  "#ef4444",
  "#14b8a6",
  "#f97316",
];

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

function iconFor(type: string): string {
  return TYPES.find((t) => t.value === type)?.icon || "🏦";
}

type FormState = {
  name: string;
  type: string;
  currency: string;
  opening_balance: string;
  icon: string;
  color: string;
  is_default: boolean;
  credit_limit: string;
  statement_close_day: string;
};

const empty: FormState = {
  name: "",
  type: "bank",
  currency: "VND",
  opening_balance: "0",
  icon: "",
  color: "#1d4ed8",
  is_default: false,
  credit_limit: "",
  statement_close_day: "",
};

function AccountForm({
  initial,
  onSubmit,
  onCancel,
  submitLabel,
}: {
  initial: FormState;
  onSubmit: (v: FormState) => Promise<void>;
  onCancel?: () => void;
  submitLabel: string;
}) {
  const [v, setV] = useState<FormState>(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    if (!v.name.trim()) {
      setErr("Tên account bắt buộc");
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

  return (
    <div className="space-y-3">
      {err && <div className="text-red-400 text-sm">{err}</div>}
      <div className="grid md:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Tên</span>
          <input
            autoFocus
            value={v.name}
            onChange={(e) => setV({ ...v, name: e.target.value })}
            className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5"
            placeholder="VD: VCB, Momo"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Loại</span>
          <select
            value={v.type}
            onChange={(e) => {
              const t = e.target.value;
              setV({
                ...v,
                type: t,
                icon: v.icon || TYPES.find((x) => x.value === t)?.icon || "",
              });
            }}
            className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5"
          >
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.icon} {t.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Currency</span>
          <input
            value={v.currency}
            onChange={(e) =>
              setV({ ...v, currency: e.target.value.toUpperCase().slice(0, 3) })
            }
            className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5 w-24"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Số dư đầu kỳ</span>
          <input
            value={v.opening_balance}
            onChange={(e) => setV({ ...v, opening_balance: e.target.value })}
            className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5"
            inputMode="decimal"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Icon (emoji)</span>
          <input
            value={v.icon}
            onChange={(e) => setV({ ...v, icon: e.target.value })}
            className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5 w-24"
            placeholder={iconFor(v.type)}
          />
        </label>
        <div className="flex flex-col gap-1 text-sm">
          <span className="muted">Màu</span>
          <div className="flex flex-wrap gap-1">
            {COLORS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setV({ ...v, color: c })}
                className={
                  "w-6 h-6 rounded-full border-2 " +
                  (v.color === c ? "border-white" : "border-transparent")
                }
                style={{ background: c }}
              />
            ))}
          </div>
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={v.is_default}
          onChange={(e) => setV({ ...v, is_default: e.target.checked })}
        />
        <span>Dùng làm account mặc định (chỉ 1 account được default)</span>
      </label>

      {v.type === "credit" && (
        <div className="grid md:grid-cols-2 gap-3 border-t border-[var(--border)] pt-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="muted">Hạn mức tín dụng</span>
            <input
              value={v.credit_limit}
              onChange={(e) => setV({ ...v, credit_limit: e.target.value })}
              inputMode="decimal"
              placeholder="VD: 50000000"
              className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="muted">Ngày chốt sao kê (1-31)</span>
            <input
              value={v.statement_close_day}
              onChange={(e) =>
                setV({ ...v, statement_close_day: e.target.value.replace(/\D/g, "") })
              }
              placeholder="VD: 15"
              className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5 w-24"
            />
          </label>
        </div>
      )}
      <div className="flex gap-2">
        <button
          onClick={save}
          disabled={busy}
          className="bg-blue-700 hover:bg-blue-600 text-white text-sm px-4 py-1.5 rounded disabled:opacity-50"
        >
          {busy ? "..." : submitLabel}
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

type BucketRef = { name: string; icon: string | null; color: string | null };

export function AccountsManager({
  initialAccounts,
  initialBalances,
  bucketByAccount = {},
}: {
  initialAccounts: Account[];
  initialBalances: Balance[];
  bucketByAccount?: Record<number, BucketRef>;
}) {
  const [accounts, setAccounts] = useState<Account[]>(initialAccounts);
  const [balances, setBalances] = useState<Balance[]>(initialBalances);
  const [bucketMap, setBucketMap] =
    useState<Record<number, BucketRef>>(bucketByAccount);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const refresh = useCallback(async () => {
    const [a, b, buckets] = await Promise.all([
      fetchJSON<Account[]>(
        "/api/v1/accounts" + (showArchived ? "?include_archived=true" : "")
      ),
      fetchJSON<Balance[]>("/api/v1/accounts/balance"),
      fetchJSON<
        { id: number; name: string; icon: string | null; color: string | null; account_ids: number[] }[]
      >("/api/v1/buckets"),
    ]);
    setAccounts(a);
    setBalances(b);
    const next: Record<number, BucketRef> = {};
    for (const bk of buckets) {
      for (const aid of bk.account_ids) {
        next[aid] = { name: bk.name, icon: bk.icon, color: bk.color };
      }
    }
    setBucketMap(next);
  }, [showArchived]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const balMap = useMemo(
    () => Object.fromEntries(balances.map((b) => [b.account_id, b])),
    [balances]
  );

  const payloadFrom = (v: FormState) => ({
    ...v,
    opening_balance: v.opening_balance || "0",
    icon: v.icon || null,
    credit_limit:
      v.type === "credit" && v.credit_limit ? v.credit_limit : null,
    statement_close_day:
      v.type === "credit" && v.statement_close_day
        ? Number(v.statement_close_day)
        : null,
  });

  const create = async (v: FormState) => {
    await fetchJSON("/api/v1/accounts", { json: payloadFrom(v) });
    setCreating(false);
    await refresh();
  };

  const update = async (id: number, v: FormState) => {
    await fetchJSON(`/api/v1/accounts/${id}`, {
      method: "PATCH",
      json: payloadFrom(v),
    });
    setEditingId(null);
    await refresh();
  };

  const archive = async (id: number, name: string) => {
    if (!confirm(`Archive account "${name}"? Lịch sử giao dịch vẫn giữ.`)) return;
    await fetchJSON(`/api/v1/accounts/${id}`, { method: "DELETE" });
    await refresh();
  };

  const unarchive = async (a: Account) => {
    await fetchJSON(`/api/v1/accounts/${a.id}`, {
      method: "PATCH",
      json: { archived: false },
    });
    await refresh();
  };

  const visible = accounts.filter((a) => showArchived || !a.archived);
  const total = balances.reduce((s, b) => s + Number(b.balance), 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Nguồn tiền</h1>
          <p className="muted text-sm">
            {visible.length} account · Tổng {fmtVND(total)}
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <label className="text-sm flex items-center gap-1">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
            />
            <span>Hiện archived</span>
          </label>
          <button
            onClick={() => {
              setCreating((c) => !c);
              setEditingId(null);
            }}
            className={creating ? "btn btn-ghost" : "btn btn-grd-primary"}
          >
            {creating ? (
              <>
                <X size={14} /> Đóng
              </>
            ) : (
              <>
                <Plus size={14} /> Thêm account
              </>
            )}
          </button>
        </div>
      </div>

      {creating && (
        <div className="card border-blue-700">
          <h2 className="font-semibold mb-3">Account mới</h2>
          <AccountForm
            initial={empty}
            submitLabel="Tạo"
            onCancel={() => setCreating(false)}
            onSubmit={create}
          />
        </div>
      )}

      <div className="grid md:grid-cols-3 gap-4">
        {visible.map((a) => {
          const bal = balMap[a.id];
          const isEditing = editingId === a.id;
          return (
            <div
              key={a.id}
              className="card"
              style={{ borderColor: a.color || undefined, opacity: a.archived ? 0.6 : 1 }}
            >
              {isEditing ? (
                <>
                  <h3 className="font-semibold mb-2 flex items-center gap-2">
                    <span>{a.icon || iconFor(a.type)}</span>
                    <span>Sửa: {a.name}</span>
                  </h3>
                  <AccountForm
                    initial={{
                      name: a.name,
                      type: a.type,
                      currency: a.currency,
                      opening_balance: a.opening_balance,
                      icon: a.icon || "",
                      color: a.color || "#1d4ed8",
                      is_default: a.is_default,
                      credit_limit: a.credit_limit ?? "",
                      statement_close_day:
                        a.statement_close_day != null ? String(a.statement_close_day) : "",
                    }}
                    submitLabel="Lưu"
                    onCancel={() => setEditingId(null)}
                    onSubmit={(v) => update(a.id, v)}
                  />
                </>
              ) : (
                <>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-2xl shrink-0">
                        {a.icon || iconFor(a.type)}
                      </span>
                      <div className="min-w-0">
                        <div className="font-semibold truncate">{a.name}</div>
                        <div className="muted text-xs uppercase tracking-wide mt-0.5">
                          {a.type}
                        </div>
                        {(a.is_default || a.archived || bucketMap[a.id]) && (
                          <div className="flex gap-1 mt-1.5 flex-wrap">
                            {a.is_default && (
                              <span className="chip chip-primary">mặc định</span>
                            )}
                            {bucketMap[a.id] && (
                              <span
                                className="chip"
                                style={{
                                  background: bucketMap[a.id].color
                                    ? `${bucketMap[a.id].color}22`
                                    : undefined,
                                  color: bucketMap[a.id].color || undefined,
                                  border: bucketMap[a.id].color
                                    ? `1px solid ${bucketMap[a.id].color}55`
                                    : undefined,
                                }}
                                title={`Bucket: ${bucketMap[a.id].name}`}
                              >
                                {bucketMap[a.id].icon || "📦"} {bucketMap[a.id].name}
                              </span>
                            )}
                            {a.archived && (
                              <span className="chip chip-muted">đã lưu trữ</span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-1 flex-shrink-0">
                      <button
                        onClick={() => {
                          setEditingId(a.id);
                          setCreating(false);
                        }}
                        title="Sửa"
                        className="bg-[var(--border)] hover:bg-gray-700 rounded p-1.5"
                      >
                        <Pencil size={14} />
                      </button>
                      {a.archived ? (
                        <button
                          onClick={() => unarchive(a)}
                          title="Unarchive"
                          className="bg-green-900 hover:bg-green-800 text-white rounded p-1.5"
                        >
                          <ArchiveRestore size={14} />
                        </button>
                      ) : (
                        <button
                          onClick={() => archive(a.id, a.name)}
                          title="Archive"
                          className="bg-red-900 hover:bg-red-800 text-white rounded p-1.5"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </div>
                  {a.type === "credit" ? (
                    <>
                      {(() => {
                        // Credit accounts go negative as you spend, positive
                        // when you over-pay. Show whichever side is non-zero
                        // so a 0-debt-but-positive-balance account isn't
                        // ambiguously labelled "Dư nợ: 0đ".
                        const balNum = Number(bal?.balance || 0);
                        const debtNum = Number(bal?.debt || 0);
                        const hasSurplus = balNum > 0;
                        const label = hasSurplus ? "Dư có (đã thanh toán dư)" : "Dư nợ";
                        const value = hasSurplus
                          ? String(balNum)
                          : (bal?.debt || "0");
                        return (
                          <div className="mt-3">
                            <div className="muted text-xs uppercase">{label}</div>
                            <div
                              className={
                                "text-xl font-mono " +
                                (hasSurplus ? "pos" : debtNum > 0 ? "neg" : "muted")
                              }
                            >
                              {fmtVND(value)}
                            </div>
                          </div>
                        );
                      })()}
                      {bal?.credit_limit ? (
                        <>
                          <div className="flex justify-between text-xs muted mt-2">
                            <span>Hạn mức còn</span>
                            <span>{fmtVND(bal.available_credit || "0")} / {fmtVND(bal.credit_limit)}</span>
                          </div>
                          <div className="w-full h-1.5 bg-[var(--border)] rounded-full overflow-hidden mt-1">
                            <div
                              className={
                                "h-full " +
                                ((bal.utilization_pct ?? 0) >= 80
                                  ? "bg-red-600"
                                  : (bal.utilization_pct ?? 0) >= 50
                                  ? "bg-yellow-500"
                                  : "bg-green-600")
                              }
                              style={{ width: `${Math.min(100, bal.utilization_pct ?? 0)}%` }}
                            />
                          </div>
                        </>
                      ) : (
                        <div className="muted text-xs mt-2">
                          Chưa set hạn mức · bấm nút sửa
                        </div>
                      )}
                      {a.statement_close_day != null && (
                        <div className="muted text-xs mt-1">
                          Chốt sao kê: ngày {a.statement_close_day}
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <div className="mt-3 text-xl font-mono">
                        {fmtVND(bal?.balance || "0")}
                      </div>
                      <div className="muted text-xs mt-1">
                        Mở {fmtVND(a.opening_balance)} · {a.currency}
                      </div>
                    </>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
