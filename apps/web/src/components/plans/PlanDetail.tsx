"use client";

import {
  ArrowLeft,
  Banknote,
  Coins,
  Pencil,
  PiggyBank,
  RotateCcw,
  Trash2,
  TrendingUp,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { fmtVND } from "@/lib/api";

type Strategy = "soft" | "envelope" | "zero_based" | "pay_yourself_first";

type Allocation = {
  id: number;
  monthly_plan_id: number;
  bucket_id: number;
  method: "amount" | "percent";
  value: string;
  rollover: boolean;
  note: string | null;
};

type Plan = {
  id: number;
  month: string;
  expected_income: string;
  strategy: Strategy;
  carry_over_enabled: boolean;
  note: string | null;
  allocations: Allocation[];
};

type BucketStatus = {
  bucket_id: number;
  bucket_name: string;
  method: "amount" | "percent";
  value: string;
  allocated: string;
  spent: string;
  carry_in: string;
  remaining: string;
  pct: number;
  status: "ok" | "warn" | "over" | "unplanned";
  rollover: boolean;
};

type Summary = {
  month: string;
  strategy: Strategy;
  expected_income: string;
  actual_income: string;
  total_allocated: string;
  total_spent: string;
  unplanned_spent: string;
  buckets: BucketStatus[];
};

type Bucket = {
  id: number;
  name: string;
  icon: string | null;
  color: string | null;
  archived: boolean;
};

const STRATEGY_OPTIONS: { value: Strategy; label: string }[] = [
  { value: "soft", label: "Hướng dẫn nhẹ (cảnh báo, không chặn)" },
  { value: "envelope", label: "Nghiêm ngặt (envelope)" },
  { value: "zero_based", label: "Zero-based (tổng = thu nhập)" },
  { value: "pay_yourself_first", label: "Pay-yourself-first" },
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

function fmtMonth(m: string): string {
  const d = new Date(m);
  return d.toLocaleDateString("vi-VN", {
    month: "long",
    year: "numeric",
  });
}

function statusColor(s: BucketStatus["status"]): string {
  return s === "over"
    ? "bg-red-600"
    : s === "warn"
      ? "bg-amber-500"
      : s === "unplanned"
        ? "bg-slate-600"
        : "bg-emerald-600";
}

type EditAlloc = {
  bucket_id: number;
  method: "amount" | "percent";
  value: string;
  rollover: boolean;
};

export function PlanDetail({
  month,
  plan,
  summary,
  buckets,
}: {
  month: string;
  plan: Plan;
  summary: Summary;
  buckets: Bucket[];
}) {
  const router = useRouter();
  const bucketById = useMemo(
    () => new Map(buckets.map((b) => [b.id, b])),
    [buckets]
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);

  const [income, setIncome] = useState(plan.expected_income);
  const [strategy, setStrategy] = useState<Strategy>(plan.strategy);
  const [carryOver, setCarryOver] = useState(plan.carry_over_enabled);
  const [note, setNote] = useState(plan.note || "");
  const [allocs, setAllocs] = useState<EditAlloc[]>(
    plan.allocations.map((a) => ({
      bucket_id: a.bucket_id,
      method: a.method,
      value: a.value,
      rollover: a.rollover,
    }))
  );

  const availableBuckets = buckets.filter(
    (b) => !allocs.some((a) => a.bucket_id === b.id)
  );

  function patchAlloc(i: number, patch: Partial<EditAlloc>) {
    setAllocs((arr) => arr.map((a, idx) => (idx === i ? { ...a, ...patch } : a)));
  }
  function removeAlloc(i: number) {
    setAllocs((arr) => arr.filter((_, idx) => idx !== i));
  }
  function addAlloc(bucket_id: number) {
    setAllocs((arr) => [
      ...arr,
      { bucket_id, method: "amount", value: "0", rollover: true },
    ]);
  }

  const expectedNum = Number(income) || 0;
  const totalEditAlloc = allocs.reduce((sum, a) => {
    const v = Number(a.value) || 0;
    return sum + (a.method === "percent" ? (expectedNum * v) / 100 : v);
  }, 0);

  async function save() {
    setErr(null);
    setBusy(true);
    try {
      await fetchJSON(`/api/v1/plans/${month}`, {
        method: "PATCH",
        json: {
          expected_income: income,
          strategy,
          carry_over_enabled: carryOver,
          note: note.trim() || null,
          allocations: allocs.map((a) => ({
            bucket_id: a.bucket_id,
            method: a.method,
            value: a.value,
            rollover: a.rollover,
          })),
        },
      });
      setEditMode(false);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function deletePlan() {
    if (!confirm(`Xoá kế hoạch tháng ${month}? (các giao dịch không bị xoá)`)) return;
    setBusy(true);
    try {
      await fetchJSON(`/api/v1/plans/${month}`, { method: "DELETE" });
      router.push("/plans");
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const actualIncomeNum = Number(summary.actual_income) || 0;
  const expectedNumSummary = Number(summary.expected_income) || 0;
  const incomeDiff = actualIncomeNum - expectedNumSummary;
  const leftToAllocate = expectedNumSummary - Number(summary.total_allocated);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <Link href="/plans" className="text-sm muted hover:underline inline-flex items-center gap-1">
            <ArrowLeft size={14} /> Danh sách kế hoạch
          </Link>
          <h1 className="text-xl font-semibold mt-1">
            Kế hoạch {fmtMonth(plan.month)}
          </h1>
        </div>
        <div className="flex gap-2">
          {!editMode && (
            <button onClick={() => setEditMode(true)} className="btn btn-grd-primary">
              <Pencil size={14} /> Chỉnh sửa
            </button>
          )}
          {editMode && (
            <>
              <button
                onClick={save}
                disabled={busy}
                className="btn btn-grd-primary"
              >
                {busy ? "…" : "Lưu"}
              </button>
              <button
                onClick={() => {
                  setEditMode(false);
                  setIncome(plan.expected_income);
                  setStrategy(plan.strategy);
                  setCarryOver(plan.carry_over_enabled);
                  setNote(plan.note || "");
                  setAllocs(
                    plan.allocations.map((a) => ({
                      bucket_id: a.bucket_id,
                      method: a.method,
                      value: a.value,
                      rollover: a.rollover,
                    }))
                  );
                  setErr(null);
                }}
                className="btn btn-ghost"
              >
                Huỷ
              </button>
            </>
          )}
          <button
            onClick={deletePlan}
            className="btn-icon hover:!text-[var(--danger)]"
            title="Xoá kế hoạch"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {err && <div className="neg text-sm">{err}</div>}

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="card">
          <div className="flex items-start justify-between mb-2">
            <span className="icon-badge icon-badge-primary">
              <Banknote size={18} strokeWidth={2.25} />
            </span>
          </div>
          <div className="text-xl font-semibold tracking-tight">
            {fmtVND(summary.expected_income)}
          </div>
          <div className="muted text-xs mt-1">Thu nhập dự kiến</div>
        </div>
        <div className="card">
          <div className="flex items-start justify-between mb-2">
            <span className="icon-badge icon-badge-success">
              <TrendingUp size={18} strokeWidth={2.25} />
            </span>
            {expectedNumSummary > 0 && (
              <span
                className={`chip ${incomeDiff >= 0 ? "chip-success" : "chip-danger"}`}
              >
                {incomeDiff >= 0 ? "+" : "-"}
                {fmtVND(Math.abs(incomeDiff))}
              </span>
            )}
          </div>
          <div className="text-xl font-semibold tracking-tight">
            {fmtVND(summary.actual_income)}
          </div>
          <div className="muted text-xs mt-1">Thu nhập thực tế</div>
        </div>
        <div className="card">
          <div className="flex items-start justify-between mb-2">
            <span className="icon-badge icon-badge-info">
              <PiggyBank size={18} strokeWidth={2.25} />
            </span>
            <span
              className={`chip ${leftToAllocate < 0 ? "chip-danger" : "chip-muted"}`}
            >
              {leftToAllocate >= 0
                ? `còn ${fmtVND(leftToAllocate)}`
                : `vượt ${fmtVND(Math.abs(leftToAllocate))}`}
            </span>
          </div>
          <div className="text-xl font-semibold tracking-tight">
            {fmtVND(summary.total_allocated)}
          </div>
          <div className="muted text-xs mt-1">Đã phân bổ</div>
        </div>
        <div className="card">
          <div className="flex items-start justify-between mb-2">
            <span className="icon-badge icon-badge-warning">
              <Coins size={18} strokeWidth={2.25} />
            </span>
            {Number(summary.unplanned_spent) > 0 && (
              <span className="chip chip-danger">
                {fmtVND(summary.unplanned_spent)} unplan
              </span>
            )}
          </div>
          <div className="text-xl font-semibold tracking-tight">
            {fmtVND(summary.total_spent)}
          </div>
          <div className="muted text-xs mt-1">Đã chi tháng này</div>
        </div>
      </div>

      {/* Plan config */}
      {editMode ? (
        <div className="card flex flex-col gap-3">
          <div className="flex gap-3 flex-wrap items-end">
            <label className="flex flex-col gap-1 text-sm">
              <span className="muted">Thu nhập dự kiến (VND)</span>
              <input
                className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5 w-44"
                value={income}
                onChange={(e) => setIncome(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="muted">Chiến lược</span>
              <select
                className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5"
                value={strategy}
                onChange={(e) => setStrategy(e.target.value as Strategy)}
              >
                {STRATEGY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm mt-5">
              <input
                type="checkbox"
                checked={carryOver}
                onChange={(e) => setCarryOver(e.target.checked)}
              />
              Cho phép carry-over từ tháng trước
            </label>
          </div>
          <label className="flex flex-col gap-1 text-sm">
            <span className="muted">Ghi chú</span>
            <input
              className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
        </div>
      ) : (
        <div className="card flex flex-wrap gap-6 text-sm">
          <div>
            <span className="muted">Chiến lược: </span>
            <span>
              {STRATEGY_OPTIONS.find((o) => o.value === plan.strategy)?.label ||
                plan.strategy}
            </span>
          </div>
          <div>
            <span className="muted">Carry-over: </span>
            <span>{plan.carry_over_enabled ? "ON" : "OFF"}</span>
          </div>
          {plan.note && (
            <div>
              <span className="muted">Ghi chú: </span>
              <span>{plan.note}</span>
            </div>
          )}
        </div>
      )}

      {/* Bucket table */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold">Phân bổ theo nhóm</h2>
          {editMode && (
            <div className="text-sm muted">
              Đang phân bổ: <span className="font-medium">{fmtVND(totalEditAlloc)}</span>
              {expectedNum > 0 && (
                <>
                  {" "}
                  /{" "}
                  <span className="font-medium">{fmtVND(expectedNum)}</span> (
                  {((totalEditAlloc / expectedNum) * 100).toFixed(1)}%)
                </>
              )}
            </div>
          )}
        </div>

        {!editMode && summary.buckets.length === 0 && (
          <div className="muted text-sm">
            Chưa có bucket nào. Bấm "Chỉnh sửa" → thêm bucket, hoặc{" "}
            <Link href="/buckets" className="underline">
              tạo bucket mới
            </Link>
            .
          </div>
        )}

        {!editMode ? (
          <div className="flex flex-col gap-3">
            {summary.buckets.map((b) => {
              const meta = bucketById.get(b.bucket_id);
              const pctClamped = Math.min(100, b.pct);
              return (
                <div key={b.bucket_id} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className="w-7 h-7 flex items-center justify-center rounded-full text-base shrink-0"
                        style={{ backgroundColor: meta?.color || "#1f2937" }}
                      >
                        {meta?.icon || "🪣"}
                      </span>
                      <span className="font-medium truncate">{b.bucket_name}</span>
                      {b.status === "unplanned" && (
                        <span className="chip chip-muted">chưa phân bổ</span>
                      )}
                      {b.rollover && (
                        <RotateCcw size={11} className="muted shrink-0" />
                      )}
                    </div>
                    <div className="text-sm text-right shrink-0">
                      <span
                        className={
                          b.status === "over"
                            ? "neg font-medium"
                            : b.status === "warn"
                              ? "text-amber-400 font-medium"
                              : ""
                        }
                      >
                        {fmtVND(b.spent)}
                      </span>
                      <span className="muted"> / {fmtVND(b.allocated)}</span>
                      {Number(b.carry_in) !== 0 && (
                        <span className="muted text-xs">
                          {" "}
                          ({Number(b.carry_in) > 0 ? "+" : ""}
                          {fmtVND(b.carry_in)} carry)
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="h-2 bg-[var(--border)] rounded overflow-hidden">
                    <div
                      className={`h-full ${statusColor(b.status)}`}
                      style={{ width: `${pctClamped}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs muted">
                    <span>
                      {b.method === "percent"
                        ? `${b.value}% thu nhập`
                        : `cố định`}
                    </span>
                    <span>
                      còn{" "}
                      <span
                        className={
                          Number(b.remaining) < 0 ? "neg" : ""
                        }
                      >
                        {fmtVND(b.remaining)}
                      </span>{" "}
                      · {b.pct.toFixed(1)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="text-xs muted grid grid-cols-[1fr_90px_140px_70px_60px_40px] gap-2 px-2">
              <div>Nhóm</div>
              <div>Kiểu</div>
              <div>Giá trị</div>
              <div className="text-right">Quy đổi</div>
              <div className="text-center">Roll</div>
              <div></div>
            </div>
            {allocs.map((a, i) => {
              const meta = bucketById.get(a.bucket_id);
              const vnum = Number(a.value) || 0;
              const resolved =
                a.method === "percent" ? (expectedNum * vnum) / 100 : vnum;
              return (
                <div
                  key={a.bucket_id}
                  className="grid grid-cols-[1fr_90px_140px_70px_60px_40px] gap-2 items-center bg-[var(--border)]/20 rounded px-2 py-1.5"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="w-6 h-6 flex items-center justify-center rounded-full text-sm shrink-0"
                      style={{ backgroundColor: meta?.color || "#1f2937" }}
                    >
                      {meta?.icon || "🪣"}
                    </span>
                    <span className="truncate">{meta?.name || `#${a.bucket_id}`}</span>
                  </div>
                  <select
                    className="bg-[var(--card)] border border-[var(--border)] rounded px-1.5 py-1 text-sm"
                    value={a.method}
                    onChange={(e) =>
                      patchAlloc(i, {
                        method: e.target.value as "amount" | "percent",
                      })
                    }
                  >
                    <option value="amount">VND</option>
                    <option value="percent">%</option>
                  </select>
                  <input
                    className="bg-[var(--card)] border border-[var(--border)] rounded px-1.5 py-1 text-sm"
                    value={a.value}
                    onChange={(e) => patchAlloc(i, { value: e.target.value })}
                  />
                  <div className="text-right text-sm muted">
                    {a.method === "percent" ? fmtVND(resolved) : "—"}
                  </div>
                  <label className="flex justify-center">
                    <input
                      type="checkbox"
                      checked={a.rollover}
                      onChange={(e) =>
                        patchAlloc(i, { rollover: e.target.checked })
                      }
                    />
                  </label>
                  <button
                    onClick={() => removeAlloc(i)}
                    className="hover:bg-red-900/40 rounded p-1 inline-flex items-center justify-center"
                    title="Xoá"
                  >
                    <X size={14} />
                  </button>
                </div>
              );
            })}
            {availableBuckets.length > 0 && (
              <div className="flex gap-2 items-center mt-1">
                <span className="text-sm muted">+ Thêm:</span>
                <select
                  className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1 text-sm"
                  defaultValue=""
                  onChange={(e) => {
                    const id = Number(e.target.value);
                    if (id) {
                      addAlloc(id);
                      e.currentTarget.value = "";
                    }
                  }}
                >
                  <option value="">— chọn nhóm —</option>
                  {availableBuckets.map((b) => (
                    <option key={b.id} value={b.id}>
                      {(b.icon || "🪣") + " " + b.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {allocs.length === 0 && (
              <div className="muted text-sm italic">
                Chưa phân bổ nhóm nào. Chọn bucket ở trên để bắt đầu.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
