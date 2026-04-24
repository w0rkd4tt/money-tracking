"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, Plus, Trash2, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Fragment, useState, useTransition } from "react";
import { fmtDate, fmtVND } from "@/lib/api";
import { TransactionForm } from "./TransactionForm";

function fmtDateGroup(d: Date): string {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const ds = new Date(d);
  ds.setHours(0, 0, 0, 0);
  const weekday = d.toLocaleDateString("vi-VN", { weekday: "long" });
  const full = d.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  if (ds.getTime() === today.getTime()) return `Hôm nay · ${full}`;
  if (ds.getTime() === yesterday.getTime()) return `Hôm qua · ${full}`;
  return `${weekday.charAt(0).toUpperCase() + weekday.slice(1)} · ${full}`;
}

type Tx = {
  id: number;
  ts: string;
  amount: string;
  currency: string;
  account_id: number;
  category_id: number | null;
  merchant_text: string | null;
  note: string | null;
  source: string;
  status: string;
  transfer_group_id: number | null;
};

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

const SOURCE_ICON: Record<string, string> = {
  manual: "✋",
  chat_web: "💬",
  chat_telegram: "🤖",
  gmail: "📧",
  agent_propose: "🧠",
};

function sourceLabel(s: string): string {
  if (s.startsWith("gmail:")) return `📧 ${s.slice(6)}`;
  return `${SOURCE_ICON[s] || "•"} ${s}`;
}

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

export function TransactionsManager({
  initialTxs,
  total,
  accounts,
  categories,
  accMap,
  catMap,
}: {
  initialTxs: Tx[];
  total: number;
  accounts: Account[];
  categories: Category[];
  accMap: Record<number, string>;
  catMap: Record<number, string>;
}) {
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [showForm, setShowForm] = useState(false);
  const pathname = usePathname();
  const sp = useSearchParams();
  const currentSort = (sp.get("sort") || "ts") as "ts" | "amount";
  const currentOrder = (sp.get("order") || "desc") as "asc" | "desc";

  function refresh() {
    startTransition(() => router.refresh());
  }

  function toggleSort(col: "ts" | "amount") {
    const next = new URLSearchParams(sp.toString());
    if (currentSort === col) {
      // Same column → flip direction
      next.set("order", currentOrder === "desc" ? "asc" : "desc");
    } else {
      // New column → default desc (newest/largest first)
      next.set("sort", col);
      next.set("order", "desc");
    }
    // Drop defaults for clean URLs
    if (next.get("sort") === "ts") next.delete("sort");
    if (next.get("order") === "desc") next.delete("order");
    const s = next.toString();
    startTransition(() => {
      router.push(pathname + (s ? `?${s}` : ""));
    });
  }

  function SortIcon({ col }: { col: "ts" | "amount" }) {
    if (currentSort !== col) {
      return <ArrowUpDown size={11} className="muted inline-block ml-1" />;
    }
    return currentOrder === "asc" ? (
      <ArrowUp size={11} className="text-[var(--primary)] inline-block ml-1" />
    ) : (
      <ArrowDown size={11} className="text-[var(--primary)] inline-block ml-1" />
    );
  }

  async function onDelete(tx: Tx) {
    if (tx.transfer_group_id) {
      alert("Giao dịch này thuộc transfer. Xoá ở trang Transfers để giữ nhất quán.");
      return;
    }
    if (!confirm(`Xoá giao dịch #${tx.id}?`)) return;
    try {
      await fetchJSON(`/api/v1/transactions/${tx.id}`, { method: "DELETE" });
      refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 flex-wrap">
        <h1 className="text-xl font-bold">Giao dịch ({total})</h1>
        <button
          onClick={() => setShowForm((s) => !s)}
          className={showForm ? "btn btn-ghost" : "btn btn-grd-primary"}
        >
          {showForm ? (
            <>
              <X size={14} /> Đóng
            </>
          ) : (
            <>
              <Plus size={14} /> Thêm giao dịch
            </>
          )}
        </button>
      </div>

      {showForm && (
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-base font-semibold">Thêm giao dịch thủ công</h2>
            <span className="text-xs muted">
              Dùng khi chat LLM bị down hoặc muốn nhập chính xác
            </span>
          </div>
          <TransactionForm
            accounts={accounts}
            categories={categories}
            onCreated={refresh}
            onCancel={() => setShowForm(false)}
          />
        </div>
      )}

      <div className="card !p-0 overflow-auto">
        <table className="table-clean">
          <thead>
            <tr>
              <th>
                <button
                  type="button"
                  onClick={() => toggleSort("ts")}
                  className="inline-flex items-center hover:text-[var(--fg)] uppercase tracking-[0.04em] text-xs font-medium"
                  title="Sắp xếp theo thời gian"
                >
                  Thời gian
                  <SortIcon col="ts" />
                </button>
              </th>
              <th>Tài khoản</th>
              <th>Category</th>
              <th>Merchant / ghi chú</th>
              <th className="text-right">
                <button
                  type="button"
                  onClick={() => toggleSort("amount")}
                  className="inline-flex items-center hover:text-[var(--fg)] uppercase tracking-[0.04em] text-xs font-medium"
                  title="Sắp xếp theo số tiền"
                >
                  Số tiền
                  <SortIcon col="amount" />
                </button>
              </th>
              <th>Nguồn</th>
              <th>Trạng thái</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(() => {
              const groupByDate = currentSort === "ts";
              let prevDateKey: string | null = null;
              return initialTxs.map((t) => {
                const statusChip =
                  t.status === "confirmed"
                    ? "chip chip-success"
                    : t.status === "pending"
                      ? "chip chip-warning"
                      : t.status === "rejected"
                        ? "chip chip-danger"
                        : "chip chip-muted";
                const d = new Date(t.ts);
                const dateKey = d.toDateString();
                const showDivider = groupByDate && dateKey !== prevDateKey;
                prevDateKey = dateKey;
                return (
                  <Fragment key={t.id}>
                    {showDivider && (
                      <tr className="bg-[var(--bg)]/60">
                        <td
                          colSpan={8}
                          className="!py-2 !px-3 text-xs muted font-medium uppercase tracking-wide sticky-ish"
                        >
                          {fmtDateGroup(d)}
                        </td>
                      </tr>
                    )}
                    <tr>
                      <td className="whitespace-nowrap text-xs">
                        {groupByDate
                          ? d.toLocaleTimeString("vi-VN", {
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : fmtDate(t.ts)}
                      </td>
                      <td>{accMap[t.account_id] || String(t.account_id)}</td>
                      <td className="muted">
                        {t.category_id ? catMap[t.category_id] : "—"}
                      </td>
                      <td>
                        {t.merchant_text || t.note || "—"}
                        {t.transfer_group_id ? " ⇄" : ""}
                      </td>
                      <td
                        className={
                          "text-right font-mono " +
                          (Number(t.amount) < 0 ? "neg" : "pos")
                        }
                      >
                        {fmtVND(t.amount)}
                      </td>
                      <td className="text-xs">{sourceLabel(t.source)}</td>
                      <td>
                        <span className={statusChip}>{t.status}</span>
                      </td>
                      <td className="text-right">
                        <button
                          onClick={() => onDelete(t)}
                          className="btn-icon hover:!text-[var(--danger)]"
                          title="Xoá"
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  </Fragment>
                );
              });
            })()}
            {initialTxs.length === 0 && (
              <tr>
                <td colSpan={8} className="py-4 muted text-center">
                  Không có giao dịch nào khớp bộ lọc.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
