"use client";

import { Check, Pencil, X } from "lucide-react";
import { useMemo, useState } from "react";

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

export type Extracted = {
  id: number | null;
  status: string;
  amount: number;
  currency: string;
  kind: string;
  account: string;
  to_account: string | null;
  category: string | null;
  merchant: string | null;
  ts: string;
  note: string | null;
  confidence: number;
};

async function jsonOrThrow(r: Response): Promise<unknown> {
  if (!r.ok) {
    let msg = await r.text();
    try {
      msg = JSON.parse(msg).detail ?? msg;
    } catch {
      // raw text
    }
    throw new Error(`${r.status}: ${msg}`);
  }
  if (r.status === 204) return null;
  return r.json();
}

export function ExtractedTxCard({
  tx,
  accounts,
  categories,
  onDone,
  onMessage,
}: {
  tx: Extracted;
  accounts: Account[];
  categories: Category[];
  onDone: (msg: string) => void;
  onMessage: (msg: string) => void;
}) {
  // An unresolved transaction arrives with id=null (LLM couldn't match account)
  const unresolved = tx.id == null;
  const kind = (tx.kind === "income" ? "income" : "expense") as
    | "expense"
    | "income";

  const activeAccounts = useMemo(
    () => accounts.filter((a) => !a.archived),
    [accounts]
  );
  const validCats = useMemo(
    () => categories.filter((c) => c.kind === kind),
    [categories, kind]
  );

  // Try to preselect what LLM returned (even if unresolved)
  const preselAccount = useMemo(() => {
    if (!tx.account) return activeAccounts[0]?.id ?? null;
    const match = activeAccounts.find(
      (a) => a.name.toLowerCase() === tx.account.toLowerCase()
    );
    return match?.id ?? activeAccounts[0]?.id ?? null;
  }, [tx.account, activeAccounts]);

  const preselCategory = useMemo(() => {
    if (!tx.category) return null;
    const match = validCats.find(
      (c) =>
        c.path.toLowerCase() === tx.category!.toLowerCase() ||
        c.name.toLowerCase() === tx.category!.toLowerCase()
    );
    return match?.id ?? null;
  }, [tx.category, validCats]);

  const needsAccount = unresolved;
  const needsCategory = !tx.category || preselCategory == null;
  const needsInput = needsAccount || needsCategory;

  const [editOpen, setEditOpen] = useState(needsInput);
  const [accountId, setAccountId] = useState<number | null>(preselAccount);
  const [categoryId, setCategoryId] = useState<number | null>(preselCategory);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [decided, setDecided] = useState<"confirmed" | "rejected" | null>(
    tx.status === "confirmed" ? "confirmed" : null
  );

  async function confirmExisting() {
    if (!tx.id) return;
    setBusy(true);
    setErr(null);
    try {
      // If user changed account/category, PATCH first, then confirm.
      if (
        accountId !== preselAccount ||
        categoryId !== preselCategory ||
        editOpen
      ) {
        const patch: Record<string, unknown> = {};
        if (accountId) patch.account_id = accountId;
        if (categoryId !== null) patch.category_id = categoryId;
        if (Object.keys(patch).length > 0) {
          await jsonOrThrow(
            await fetch(`/api/v1/transactions/${tx.id}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(patch),
            })
          );
        }
      }
      await jsonOrThrow(
        await fetch(`/api/v1/transactions/${tx.id}/confirm`, {
          method: "POST",
        })
      );
      setDecided("confirmed");
      onDone(`#${tx.id} đã confirm ✓`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function rejectExisting() {
    if (!tx.id) return;
    setBusy(true);
    setErr(null);
    try {
      await jsonOrThrow(
        await fetch(`/api/v1/transactions/${tx.id}/reject`, {
          method: "POST",
        })
      );
      setDecided("rejected");
      onDone(`#${tx.id} đã huỷ ✗`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function createNew() {
    if (!accountId) {
      setErr("Chọn tài khoản trước");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const signedAmount = kind === "expense" ? -Math.abs(tx.amount) : Math.abs(tx.amount);
      const body = {
        ts: tx.ts,
        amount: String(signedAmount),
        currency: tx.currency || "VND",
        account_id: accountId,
        category_id: categoryId,
        merchant_text: tx.merchant,
        note: tx.note,
        source: "chat_web",
        status: "confirmed",
      };
      const created = (await jsonOrThrow(
        await fetch("/api/v1/transactions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        })
      )) as { id: number };
      setDecided("confirmed");
      onDone(`#${created.id} đã tạo ✓`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const accountByIdName = (id: number | null): string => {
    if (!id) return "—";
    return activeAccounts.find((a) => a.id === id)?.name || String(id);
  };
  const categoryByIdName = (id: number | null): string => {
    if (!id) return "Chưa phân loại";
    return validCats.find((c) => c.id === id)?.path || String(id);
  };

  if (decided === "confirmed") {
    return (
      <div className="card !py-2 !px-3 flex items-center gap-2 text-xs muted bg-emerald-950/20 border-emerald-900/50">
        <Check size={14} className="text-[var(--success)]" />
        Đã xác nhận · {accountByIdName(accountId)} · {categoryByIdName(categoryId)}
      </div>
    );
  }
  if (decided === "rejected") {
    return (
      <div className="card !py-2 !px-3 flex items-center gap-2 text-xs muted">
        <X size={14} className="text-[var(--danger)]" /> Đã huỷ
      </div>
    );
  }

  return (
    <div
      className={`card ${needsInput && !editOpen ? "" : "border-amber-900/40 bg-amber-950/10"}`}
    >
      <div className="flex justify-between items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-lg tracking-tight">
            {kind === "expense" ? "−" : tx.kind === "transfer" ? "⇄" : "+"}
            {new Intl.NumberFormat("vi-VN").format(tx.amount)} {tx.currency}
          </div>
          {tx.merchant && (
            <div className="text-xs muted mt-0.5">{tx.merchant}</div>
          )}
          {tx.note && !tx.merchant && (
            <div className="text-xs muted mt-0.5 italic">"{tx.note}"</div>
          )}
        </div>
      </div>

      {/* Field display/edit */}
      <div className="mt-3 grid grid-cols-1 gap-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="muted w-20 text-xs uppercase tracking-wide">
            Tài khoản
          </span>
          {editOpen ? (
            <select
              className="field flex-1 !py-1"
              value={accountId ?? ""}
              onChange={(e) =>
                setAccountId(e.target.value ? Number(e.target.value) : null)
              }
            >
              <option value="">— chọn —</option>
              {activeAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.icon ? `${a.icon} ` : ""}
                  {a.name}
                </option>
              ))}
            </select>
          ) : (
            <span className="flex-1">
              {accountByIdName(accountId)}
              {needsAccount && (
                <span className="chip chip-warning ml-2">cần chọn</span>
              )}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <span className="muted w-20 text-xs uppercase tracking-wide">
            Danh mục
          </span>
          {editOpen ? (
            <select
              className="field flex-1 !py-1"
              value={categoryId ?? ""}
              onChange={(e) =>
                setCategoryId(e.target.value ? Number(e.target.value) : null)
              }
            >
              <option value="">— không phân loại —</option>
              {validCats.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.path || c.name}
                </option>
              ))}
            </select>
          ) : (
            <span className="flex-1">
              {categoryByIdName(categoryId)}
              {needsCategory && (
                <span className="chip chip-warning ml-2">chưa phân loại</span>
              )}
            </span>
          )}
        </div>
      </div>

      {err && <div className="neg text-xs mt-2">{err}</div>}

      <div className="flex gap-2 mt-3 items-center flex-wrap">
        {unresolved ? (
          <button
            type="button"
            onClick={createNew}
            disabled={busy || !accountId}
            className="btn btn-grd-primary !py-1.5"
          >
            {busy ? "…" : "Tạo giao dịch"}
          </button>
        ) : (
          <button
            type="button"
            onClick={confirmExisting}
            disabled={busy}
            className="btn btn-grd-primary !py-1.5"
          >
            {busy ? "…" : (
              <>
                <Check size={13} /> Lưu & xác nhận
              </>
            )}
          </button>
        )}
        {!unresolved && (
          <button
            type="button"
            onClick={rejectExisting}
            disabled={busy}
            className="btn btn-danger !py-1.5"
          >
            <X size={13} /> Huỷ
          </button>
        )}
        {!editOpen && (
          <button
            type="button"
            onClick={() => setEditOpen(true)}
            className="btn btn-ghost !py-1.5"
            title="Sửa trước khi xác nhận"
          >
            <Pencil size={13} /> Sửa
          </button>
        )}
        {editOpen && !needsInput && (
          <button
            type="button"
            onClick={() => {
              setEditOpen(false);
              setAccountId(preselAccount);
              setCategoryId(preselCategory);
              setErr(null);
            }}
            className="btn btn-ghost !py-1.5"
          >
            Bỏ sửa
          </button>
        )}
      </div>
    </div>
  );
}

// Explicitly export to suppress unused-var lint when onMessage isn't used yet.
export type ExtractedTxCardHooks = {
  onDone?: (msg: string) => void;
  onMessage?: (msg: string) => void;
};
