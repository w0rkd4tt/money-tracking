"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fmtDate, fmtVND } from "@/lib/api";

type IngestedItem = {
  transaction_id: number;
  ts: string;
  amount: string;
  currency: string;
  status: string;
  confidence: number;
  account_id: number;
  account_name: string | null;
  category_id: number | null;
  category_name: string | null;
  merchant: string | null;
  note: string | null;
  rule_name: string | null;
  sender: string | null;
  subject: string | null;
  message_id: string | null;
  is_llm_fallback: boolean;
};

type Category = {
  id: number;
  name: string;
  path: string;
  kind: "expense" | "income" | "transfer";
};

type Stats = {
  total: number;
  by_rule: Record<string, number>;
  by_status: Record<string, number>;
  by_confidence: Record<string, number>;
  llm_fallback_count: number;
  rule_count: number;
};

async function jfetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { cache: "no-store", ...init });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  if (r.status === 204) return undefined as T;
  return r.json();
}

type CreditAccount = { id: number; name: string };

export function EmailIngestDashboard({
  initialItems,
  initialStats,
  categories = [],
  creditAccounts = [],
}: {
  initialItems: IngestedItem[];
  initialStats: Stats;
  categories?: Category[];
  creditAccounts?: CreditAccount[];
}) {
  const [items, setItems] = useState<IngestedItem[]>(initialItems);
  const [stats, setStats] = useState<Stats>(initialStats);
  const [filterRule, setFilterRule] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [savingCatFor, setSavingCatFor] = useState<number | null>(null);
  const [editingCatFor, setEditingCatFor] = useState<number | null>(null);
  // Per-row chosen credit account for "Thanh toán thẻ TD" linkage. Auto-fills
  // when there's exactly one credit account so the user only has to confirm.
  const [creditDestFor, setCreditDestFor] = useState<Record<number, number>>(() => {
    if (creditAccounts.length !== 1) return {};
    return {}; // populated lazily when row matches the credit-payment pattern
  });

  // Lookup by id for fast re-rendering after patch + to get path/name.
  const catById = useMemo(
    () => new Map(categories.map((c) => [c.id, c])),
    [categories]
  );

  async function saveCategory(txId: number, newCategoryId: number | null) {
    setSavingCatFor(txId);
    try {
      const r = await fetch(`/api/v1/transactions/${txId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category_id: newCategoryId }),
        cache: "no-store",
      });
      if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
      const resolved = newCategoryId != null ? catById.get(newCategoryId) : null;
      setItems((arr) =>
        arr.map((it) =>
          it.transaction_id === txId
            ? {
                ...it,
                category_id: newCategoryId,
                category_name: resolved ? resolved.path : null,
              }
            : it
        )
      );
    } catch (e) {
      alert(`Lỗi: ${(e as Error).message}`);
    } finally {
      setSavingCatFor(null);
    }
  }

  const refresh = useCallback(async () => {
    const [it, st] = await Promise.all([
      jfetch<IngestedItem[]>("/api/v1/gmail/ingested?limit=200"),
      jfetch<Stats>("/api/v1/gmail/ingest-stats"),
    ]);
    setItems(it);
    setStats(st);
  }, []);

  const sync = async () => {
    setSyncing(true);
    setSyncMsg("⏳ Đang sync nền (có thể 1–5 phút, LLM extract tốn thời gian)…");
    try {
      // Fire-and-forget kick: server returns 200 immediately, actual work runs
      // in a BackgroundTask on FastAPI side. We then poll /sync/status until
      // it reports `running=false` with a `last_result`.
      await jfetch<{ ok: boolean; message: string }>("/api/v1/gmail/sync", {
        method: "POST",
      });

      type StatusResp = {
        running: boolean;
        last_result: null | {
          ok: boolean;
          processed: number;
          ingested: number;
          skipped: number;
          errors: number;
          marked_read: number;
          llm_fallback_used: number;
          message: string;
          finished_at?: string;
        };
      };
      // Capture baseline so we detect a NEW result (not an old cached one)
      const baseline = await jfetch<StatusResp>("/api/v1/gmail/sync/status");
      const baselineFinishedAt = baseline.last_result?.finished_at ?? null;

      // Poll up to 10 minutes at 3s intervals. LLM-heavy syncs (each email
      // triggers a 5–10s classifier call) can push past 4 minutes when there
      // are 20+ emails to process. Refresh the table every 6s so the user
      // sees new pending rows appearing rather than a frozen UI.
      const POLL_TIMEOUT_MS = 10 * 60 * 1000;
      const started = Date.now();
      let final: StatusResp["last_result"] = null;
      let pollCount = 0;
      while (Date.now() - started < POLL_TIMEOUT_MS) {
        await new Promise((r) => setTimeout(r, 3000));
        pollCount++;
        const s = await jfetch<StatusResp>("/api/v1/gmail/sync/status");
        if (
          !s.running &&
          s.last_result &&
          s.last_result.finished_at !== baselineFinishedAt
        ) {
          final = s.last_result;
          break;
        }
        // Live progress: refresh the table (and elapsed counter) every 2nd
        // poll so the user sees rows trickling in.
        if (pollCount % 2 === 0) {
          const elapsed = Math.floor((Date.now() - started) / 1000);
          setSyncMsg(`⏳ Đang sync… ${elapsed}s (LLM extract đang chạy)`);
          // fire-and-forget — don't await so polling rhythm stays steady
          void refresh();
        }
      }
      if (final) {
        setSyncMsg(
          final.ok
            ? `✓ processed ${final.processed} · ingested ${final.ingested} · LLM ${final.llm_fallback_used} · marked ${final.marked_read}`
            : `❌ ${final.message}`
        );
      } else {
        setSyncMsg(
          "⚠ Timeout 10 phút — server có thể vẫn đang chạy nền, refresh sau ít phút.",
        );
      }
      await refresh();
    } catch (e) {
      setSyncMsg(`❌ ${(e as Error).message}`);
    } finally {
      setSyncing(false);
    }
  };

  // Match a category name that means "I'm paying a credit-card bill". Used
  // to surface the credit-account picker on rows like Timo "Mô tả: Tra no
  // tin dung HSBC".
  const isCreditPaymentCategory = (name: string | null): boolean => {
    if (!name) return false;
    const n = name.toLowerCase();
    return (
      n.includes("thanh toán thẻ td") ||
      n.includes("dư nợ thẻ tín dụng") ||
      n.includes("trả nợ thẻ")
    );
  };

  const confirm = async (id: number) => {
    // If the row is a credit-card payment AND a destination credit account
    // is resolved (user-picked OR the lone existing credit account), link
    // the transfer pair BEFORE flipping status. Both legs (source +
    // credit-leg) then appear together and the credit account's debt
    // updates immediately.
    const it = items.find((x) => x.transaction_id === id);
    // Match the same auto-pick fallback shown in the select's `value`
    // attribute — otherwise single-credit users would see HSBC pre-selected
    // but the state would be undefined and the link call would skip.
    const dest =
      creditDestFor[id] ??
      (creditAccounts.length === 1 ? creditAccounts[0].id : undefined);
    if (it && isCreditPaymentCategory(it.category_name) && dest) {
      try {
        const r = await fetch(
          `/api/v1/transactions/${id}/link-credit-payment`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credit_account_id: dest }),
            cache: "no-store",
          },
        );
        if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
      } catch (e) {
        alert(
          `Không link được thẻ TD: ${(e as Error).message}. Tx vẫn confirm.`,
        );
      }
    }
    await jfetch(`/api/v1/transactions/${id}/confirm`, { method: "POST" });
    await refresh();
  };
  const reject = async (id: number) => {
    await jfetch(`/api/v1/transactions/${id}/reject`, { method: "POST" });
    await refresh();
  };

  const visible = useMemo(() => {
    return items.filter((it) => {
      if (filterStatus !== "all" && it.status !== filterStatus) return false;
      if (filterRule === "all") return true;
      if (filterRule === "llm") return it.is_llm_fallback;
      if (filterRule === "rule") return !it.is_llm_fallback;
      return it.rule_name === filterRule;
    });
  }, [items, filterRule, filterStatus]);

  const rules = useMemo(() => Object.keys(stats.by_rule).sort(), [stats]);

  const confPct = (c: number) => Math.round(c * 100);
  const confColor = (c: number) =>
    c >= 0.9 ? "text-green-400" : c >= 0.7 ? "text-yellow-400" : "text-red-400";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">📧 Email ingestion</h1>
          <p className="muted text-sm">
            Theo dõi email được parse thành giao dịch (rule engine + LLM fallback).
          </p>
        </div>
        <div className="flex gap-2 items-center">
          {syncMsg && <span className="text-xs muted">{syncMsg}</span>}
          <button
            onClick={sync}
            disabled={syncing}
            className="bg-blue-700 hover:bg-blue-600 text-white text-sm px-3 py-1.5 rounded disabled:opacity-50"
          >
            {syncing ? "⏳ sync…" : "↻ Sync now"}
          </button>
          <button
            onClick={refresh}
            className="bg-[var(--border)] hover:bg-gray-700 text-sm px-3 py-1.5 rounded"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* KPI cards */}
      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="card">
          <div className="muted text-xs uppercase">Tổng ingested</div>
          <div className="text-2xl font-semibold">{stats.total}</div>
        </div>
        <div className="card">
          <div className="muted text-xs uppercase">Rule engine</div>
          <div className="text-2xl font-semibold pos">{stats.rule_count}</div>
        </div>
        <div className="card">
          <div className="muted text-xs uppercase">LLM fallback</div>
          <div className="text-2xl font-semibold text-purple-400">
            {stats.llm_fallback_count}
          </div>
        </div>
        <div className="card">
          <div className="muted text-xs uppercase">Confidence cao</div>
          <div className="text-2xl font-semibold text-green-400">
            {stats.by_confidence.high || 0}
          </div>
          <div className="muted text-xs">≥ 90%</div>
        </div>
        <div className="card">
          <div className="muted text-xs uppercase">Pending</div>
          <div className="text-2xl font-semibold text-yellow-400">
            {stats.by_status.pending || 0}
          </div>
        </div>
      </section>

      {/* Breakdown */}
      <section className="grid md:grid-cols-2 gap-3">
        <div className="card">
          <h3 className="font-semibold mb-2">Phân bổ theo rule</h3>
          <ul className="text-sm space-y-1">
            {rules.length === 0 && <p className="muted">Chưa có data.</p>}
            {rules.map((r) => (
              <li key={r} className="flex justify-between">
                <span className={r === "llm-fallback" ? "text-purple-400" : ""}>
                  {r === "llm-fallback" ? "🧠 llm-fallback" : `📐 ${r}`}
                </span>
                <span className="font-mono">{stats.by_rule[r]}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="card">
          <h3 className="font-semibold mb-2">Phân bổ confidence</h3>
          <div className="flex flex-col gap-2 text-sm">
            {[
              { key: "high", label: "≥ 90%", color: "bg-green-600" },
              { key: "mid", label: "70–89%", color: "bg-yellow-600" },
              { key: "low", label: "< 70%", color: "bg-red-600" },
            ].map((b) => {
              const n = stats.by_confidence[b.key] || 0;
              const pct = stats.total ? (n / stats.total) * 100 : 0;
              return (
                <div key={b.key}>
                  <div className="flex justify-between text-xs muted">
                    <span>{b.label}</span>
                    <span>
                      {n} · {pct.toFixed(0)}%
                    </span>
                  </div>
                  <div className="w-full h-2 bg-[var(--border)] rounded-full overflow-hidden mt-1">
                    <div
                      className={`h-full ${b.color}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Filters */}
      <section className="card flex flex-wrap gap-3 items-center text-sm">
        <span className="muted">Filter:</span>
        <select
          value={filterRule}
          onChange={(e) => setFilterRule(e.target.value)}
          className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1"
        >
          <option value="all">Tất cả nguồn</option>
          <option value="rule">Rule only</option>
          <option value="llm">LLM only</option>
          {rules.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1"
        >
          <option value="all">Tất cả trạng thái</option>
          <option value="pending">Pending</option>
          <option value="confirmed">Confirmed</option>
          <option value="rejected">Rejected</option>
        </select>
        <span className="muted">
          {visible.length} / {items.length} hiển thị
        </span>
      </section>

      {/* Table */}
      <section className="card overflow-auto">
        {visible.length === 0 ? (
          <p className="muted text-sm">Chưa có email nào được parse.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="muted text-left border-b border-[var(--border)]">
                <th className="pb-2">Thời gian</th>
                <th>Nguồn</th>
                <th>Account</th>
                <th className="text-right">Amount</th>
                <th>Merchant / Subject</th>
                <th>Category</th>
                <th>Rule</th>
                <th>Conf</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((it) => (
                <tr key={it.transaction_id} className="border-b border-[var(--border)]">
                  <td className="py-2 whitespace-nowrap">{fmtDate(it.ts)}</td>
                  <td
                    className="max-w-[200px] truncate muted"
                    title={it.sender || ""}
                  >
                    {it.sender || "—"}
                  </td>
                  <td>{it.account_name || it.account_id}</td>
                  <td
                    className={
                      "text-right font-mono " +
                      (Number(it.amount) < 0 ? "neg" : "pos")
                    }
                  >
                    {fmtVND(it.amount)}
                  </td>
                  <td className="max-w-[260px] truncate" title={it.note || ""}>
                    <div>{it.merchant || "—"}</div>
                    {it.note && (
                      <div className="muted text-xs truncate">{it.note}</div>
                    )}
                  </td>
                  <td className="max-w-[220px]">
                    {it.status === "pending" ? (
                      editingCatFor === it.transaction_id ? (
                        <CategoryPicker
                          amount={it.amount}
                          categories={categories}
                          currentId={it.category_id}
                          busy={savingCatFor === it.transaction_id}
                          onCommit={(id) => {
                            setEditingCatFor(null);
                            if (id !== it.category_id) {
                              saveCategory(it.transaction_id, id);
                            }
                          }}
                        />
                      ) : (
                        <button
                          type="button"
                          onClick={() => setEditingCatFor(it.transaction_id)}
                          className="inline-flex items-center gap-1 group text-left"
                          title="Click để sửa danh mục"
                        >
                          {it.category_name ? (
                            <span
                              className={
                                it.category_name === "Chưa phân loại"
                                  ? "chip chip-muted group-hover:brightness-125"
                                  : "chip chip-primary group-hover:brightness-125"
                              }
                            >
                              {it.category_name}
                            </span>
                          ) : (
                            <span className="chip chip-warning group-hover:brightness-125">
                              — chọn danh mục
                            </span>
                          )}
                        </button>
                      )
                    ) : it.category_name ? (
                      <span
                        className={
                          it.category_name === "Chưa phân loại"
                            ? "chip chip-muted"
                            : "chip chip-primary"
                        }
                        title={it.category_name}
                      >
                        {it.category_name}
                      </span>
                    ) : (
                      <span className="muted text-xs italic">—</span>
                    )}
                  </td>
                  <td>
                    {it.is_llm_fallback ? (
                      <span className="text-xs bg-purple-900/50 text-purple-300 rounded-full px-2 py-0.5">
                        🧠 LLM
                      </span>
                    ) : (
                      <span className="text-xs bg-blue-900/50 text-blue-300 rounded-full px-2 py-0.5">
                        📐 {it.rule_name || "rule"}
                      </span>
                    )}
                  </td>
                  <td className={confColor(it.confidence)}>
                    {confPct(it.confidence)}%
                  </td>
                  <td>
                    <span
                      className={
                        "text-xs px-2 py-0.5 rounded-full " +
                        (it.status === "confirmed"
                          ? "bg-green-900/50 text-green-300"
                          : it.status === "pending"
                          ? "bg-yellow-900/50 text-yellow-300"
                          : "bg-red-900/50 text-red-300")
                      }
                    >
                      {it.status}
                    </span>
                  </td>
                  <td>
                    {it.status === "pending" && (
                      <div className="flex flex-col gap-1">
                        {isCreditPaymentCategory(it.category_name) &&
                          creditAccounts.length > 0 && (
                            <select
                              value={
                                creditDestFor[it.transaction_id] ??
                                (creditAccounts.length === 1
                                  ? creditAccounts[0].id
                                  : "")
                              }
                              onChange={(e) => {
                                const v = e.target.value;
                                setCreditDestFor((m) => ({
                                  ...m,
                                  [it.transaction_id]: Number(v),
                                }));
                              }}
                              className="field !py-0.5 !text-[10px] max-w-[120px]"
                              title="Chọn thẻ TD đích — confirm sẽ tự link transfer"
                            >
                              {creditAccounts.length > 1 && (
                                <option value="">— thẻ TD —</option>
                              )}
                              {creditAccounts.map((ca) => (
                                <option key={ca.id} value={ca.id}>
                                  → {ca.name}
                                </option>
                              ))}
                            </select>
                          )}
                        <div className="flex gap-1">
                          <button
                            onClick={() => confirm(it.transaction_id)}
                            className="text-xs bg-green-700 hover:bg-green-600 text-white rounded px-2 py-0.5"
                          >
                            ✓
                          </button>
                          <button
                            onClick={() => reject(it.transaction_id)}
                            className="text-xs bg-red-800 hover:bg-red-700 text-white rounded px-2 py-0.5"
                          >
                            ✗
                          </button>
                        </div>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}


/**
 * Inline category picker rendered while a pending row is in edit mode. Holds
 * its own draft value and commits once on blur (i.e. click-outside). Parent
 * decides whether to persist based on whether the committed id actually changed.
 * Filters by tx kind with an "Khác" fallback for edge cases like refunds.
 */
function CategoryPicker({
  amount,
  categories,
  currentId,
  busy,
  onCommit,
}: {
  amount: string;
  categories: Category[];
  currentId: number | null;
  busy: boolean;
  onCommit: (id: number | null) => void;
}) {
  const kind: "expense" | "income" =
    Number(amount) < 0 ? "expense" : "income";
  const primary = categories.filter((c) => c.kind === kind);
  const other = categories.filter((c) => c.kind !== kind);
  const [draft, setDraft] = useState<string>(
    currentId != null ? String(currentId) : ""
  );
  const selectRef = useRef<HTMLSelectElement | null>(null);

  // Auto-open the dropdown on mount so user only clicks once (chip click →
  // enters edit mode → dropdown opens immediately). `showPicker` is the modern
  // API and works on <select> in recent Chromium/Safari/Firefox. Fall back
  // silently if unavailable — user still sees the focused select.
  useEffect(() => {
    const el = selectRef.current;
    if (!el) return;
    try {
      el.showPicker?.();
    } catch {
      // Some browsers throw if called outside a user gesture; ignore.
    }
  }, []);

  return (
    <select
      ref={selectRef}
      autoFocus
      className="field !py-1 !text-xs max-w-[200px] cursor-pointer"
      value={draft}
      disabled={busy}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => onCommit(draft ? Number(draft) : null)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          onCommit(draft ? Number(draft) : null);
        } else if (e.key === "Escape") {
          e.preventDefault();
          onCommit(currentId);
        }
      }}
      title="Chọn danh mục rồi click ra ngoài để lưu"
    >
      <option value="">— chưa phân loại —</option>
      <optgroup label={kind === "expense" ? "📉 Chi tiêu" : "📈 Thu nhập"}>
        {primary.map((c) => (
          <option key={c.id} value={c.id}>
            {c.path || c.name}
          </option>
        ))}
      </optgroup>
      {other.length > 0 && (
        <optgroup label="Khác">
          {other.map((c) => (
            <option key={c.id} value={c.id}>
              [{c.kind}] {c.path || c.name}
            </option>
          ))}
        </optgroup>
      )}
    </select>
  );
}
