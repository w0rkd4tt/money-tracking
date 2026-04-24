"use client";

import { Search, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

type Account = {
  id: number;
  name: string;
  archived: boolean;
  icon?: string | null;
};

type Category = {
  id: number;
  name: string;
  path: string;
  kind: "expense" | "income" | "transfer";
};

export function TransactionFilters({
  accounts,
  categories,
}: {
  accounts: Account[];
  categories: Category[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [, startTransition] = useTransition();

  // Dropdowns read directly from URL (so Back/Forward works).
  const accountId = sp.get("account_id") || "";
  const categoryId = sp.get("category_id") || "";
  const status = sp.get("status") || "";

  // Text + date: local state, synced to URL on Apply / Enter.
  const [q, setQ] = useState(sp.get("q") || "");
  const [from, setFrom] = useState(sp.get("from") || "");
  const [to, setTo] = useState(sp.get("to") || "");

  // Resync local state when URL changes externally (sidebar click, back/forward)
  useEffect(() => {
    setQ(sp.get("q") || "");
    setFrom(sp.get("from") || "");
    setTo(sp.get("to") || "");
  }, [sp]);

  function push(next: URLSearchParams) {
    const s = next.toString();
    startTransition(() => {
      router.push(pathname + (s ? `?${s}` : ""));
    });
  }

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(sp.toString());
    if (value == null || value === "") next.delete(key);
    else next.set(key, value);
    push(next);
  }

  function applyTextAndDates() {
    const next = new URLSearchParams(sp.toString());
    if (q.trim()) next.set("q", q.trim());
    else next.delete("q");
    if (from) next.set("from", from);
    else next.delete("from");
    if (to) next.set("to", to);
    else next.delete("to");
    push(next);
  }

  function reset() {
    setQ("");
    setFrom("");
    setTo("");
    startTransition(() => router.push(pathname));
  }

  const activeCount =
    (accountId ? 1 : 0) +
    (categoryId ? 1 : 0) +
    (status ? 1 : 0) +
    (q ? 1 : 0) +
    (from ? 1 : 0) +
    (to ? 1 : 0);

  const expenseCats = categories.filter((c) => c.kind === "expense");
  const incomeCats = categories.filter((c) => c.kind === "income");
  const transferCats = categories.filter((c) => c.kind === "transfer");

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Search size={14} className="muted" />
          <span className="text-sm font-medium">Bộ lọc</span>
          {activeCount > 0 && (
            <span className="chip chip-primary">{activeCount} đang áp dụng</span>
          )}
        </div>
        {activeCount > 0 && (
          <button
            type="button"
            onClick={reset}
            className="btn btn-ghost !py-1 !text-xs"
            title="Xoá tất cả bộ lọc"
          >
            <X size={12} /> Reset
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {/* Search */}
        <label className="flex flex-col gap-1 text-sm lg:col-span-2">
          <span className="muted text-xs uppercase tracking-wide">Tìm kiếm</span>
          <div className="flex gap-2">
            <input
              className="field flex-1"
              placeholder="merchant / ghi chú…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") applyTextAndDates();
              }}
            />
            <button
              type="button"
              onClick={applyTextAndDates}
              className="btn btn-grd-primary !py-1.5"
              title="Áp dụng tìm kiếm + ngày (hoặc bấm Enter)"
            >
              Áp dụng
            </button>
          </div>
        </label>

        {/* Status */}
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted text-xs uppercase tracking-wide">Trạng thái</span>
          <select
            className="field"
            value={status}
            onChange={(e) => setParam("status", e.target.value || null)}
          >
            <option value="">Tất cả</option>
            <option value="pending">Pending</option>
            <option value="confirmed">Confirmed</option>
            <option value="rejected">Rejected</option>
          </select>
        </label>

        {/* From date */}
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted text-xs uppercase tracking-wide">Từ ngày</span>
          <input
            type="date"
            className="field"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            onBlur={applyTextAndDates}
          />
        </label>

        {/* To date */}
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted text-xs uppercase tracking-wide">Đến ngày</span>
          <input
            type="date"
            className="field"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            onBlur={applyTextAndDates}
          />
        </label>

        {/* Account */}
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted text-xs uppercase tracking-wide">Tài khoản</span>
          <select
            className="field"
            value={accountId}
            onChange={(e) => setParam("account_id", e.target.value || null)}
          >
            <option value="">Tất cả tài khoản</option>
            {accounts
              .filter((a) => !a.archived)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.icon ? `${a.icon} ` : ""}
                  {a.name}
                </option>
              ))}
          </select>
        </label>

        {/* Category */}
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted text-xs uppercase tracking-wide">Danh mục</span>
          <select
            className="field"
            value={categoryId}
            onChange={(e) => setParam("category_id", e.target.value || null)}
          >
            <option value="">Tất cả danh mục</option>
            {expenseCats.length > 0 && (
              <optgroup label="📉 Chi tiêu">
                {expenseCats.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.path || c.name}
                  </option>
                ))}
              </optgroup>
            )}
            {incomeCats.length > 0 && (
              <optgroup label="📈 Thu nhập">
                {incomeCats.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.path || c.name}
                  </option>
                ))}
              </optgroup>
            )}
            {transferCats.length > 0 && (
              <optgroup label="⇄ Transfer">
                {transferCats.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.path || c.name}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
      </div>
    </div>
  );
}
