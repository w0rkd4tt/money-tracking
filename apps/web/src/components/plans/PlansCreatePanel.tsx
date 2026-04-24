"use client";

import { Copy } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { fmtVND } from "@/lib/api";

type Bucket = { id: number; name: string };

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

function currentYearMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function prevYearMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(y, m - 2, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const PRESETS: {
  key: string;
  label: string;
  desc: string;
  apply: (bucket_ids: number[]) => { bucket_id: number; method: "percent"; value: number }[];
}[] = [
  {
    key: "50_30_20",
    label: "50 / 30 / 20",
    desc: "Thiết yếu 50% · Mong muốn 30% · Tiết kiệm 20% (cần đúng 3 nhóm)",
    apply: (ids) => {
      if (ids.length !== 3) return [];
      return [
        { bucket_id: ids[0], method: "percent", value: 50 },
        { bucket_id: ids[1], method: "percent", value: 30 },
        { bucket_id: ids[2], method: "percent", value: 20 },
      ];
    },
  },
  {
    key: "equal",
    label: "Chia đều",
    desc: "Mỗi nhóm cùng %",
    apply: (ids) => {
      if (ids.length === 0) return [];
      const pct = Math.floor(10000 / ids.length) / 100;
      return ids.map((bid) => ({ bucket_id: bid, method: "percent" as const, value: pct }));
    },
  },
];

export function PlansCreatePanel({
  buckets,
  existingMonths,
}: {
  buckets: Bucket[];
  existingMonths: string[];
}) {
  const router = useRouter();
  const existingSet = new Set(existingMonths.map((m) => m.slice(0, 7)));

  const [month, setMonth] = useState<string>(currentYearMonth());
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [suggestedIncome, setSuggestedIncome] = useState<string | null>(null);

  const prev = prevYearMonth(month);
  const hasPrev = existingSet.has(prev);
  const alreadyExists = existingSet.has(month);

  async function doSuggest() {
    setErr(null);
    try {
      const r = await fetchJSON<{ suggested: string; method: string }>(
        `/api/v1/plans/suggest-income?month=${month}`
      );
      setSuggestedIncome(r.suggested);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function doCreate(
    income: string,
    allocations: { bucket_id: number; method: "percent" | "amount"; value: number }[]
  ) {
    setErr(null);
    setBusy(true);
    try {
      await fetchJSON("/api/v1/plans", {
        json: {
          month: `${month}-01`,
          expected_income: income,
          strategy: "soft",
          carry_over_enabled: true,
          allocations: allocations.map((a) => ({
            bucket_id: a.bucket_id,
            method: a.method,
            value: String(a.value),
            rollover: true,
          })),
        },
      });
      router.push(`/plans/${month}`);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doCopyFromPrev() {
    setErr(null);
    setBusy(true);
    try {
      await fetchJSON(`/api/v1/plans/${month}/copy-from/${prev}`, { method: "POST" });
      router.push(`/plans/${month}`);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doCreatePreset(presetKey: string) {
    const preset = PRESETS.find((p) => p.key === presetKey);
    if (!preset) return;
    const allocations = preset.apply(buckets.map((b) => b.id));
    if (allocations.length === 0) {
      setErr(
        preset.key === "50_30_20"
          ? "Cần đúng 3 bucket theo thứ tự Thiết yếu/Mong muốn/Tiết kiệm"
          : "Cần ít nhất 1 bucket"
      );
      return;
    }
    await doCreate(suggestedIncome || "0", allocations);
  }

  async function doCreateEmpty() {
    await doCreate(suggestedIncome || "0", []);
  }

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-end gap-3 flex-wrap">
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Tháng</span>
          <input
            type="month"
            className="field"
            value={month}
            onChange={(e) => {
              setMonth(e.target.value);
              setSuggestedIncome(null);
            }}
          />
        </label>
        <button type="button" onClick={doSuggest} className="btn btn-ghost">
          Gợi ý thu nhập
        </button>
        {suggestedIncome && (
          <span className="text-sm">
            <span className="muted">Trung bình 3 tháng: </span>
            <span className="font-medium">{fmtVND(suggestedIncome)}</span>
          </span>
        )}
      </div>

      {alreadyExists ? (
        <div className="text-sm neg">
          Kế hoạch cho {month} đã tồn tại.{" "}
          <a href={`/plans/${month}`} className="underline">
            Mở chi tiết →
          </a>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2 items-center">
            {hasPrev && (
              <button
                type="button"
                disabled={busy}
                onClick={doCopyFromPrev}
                className="btn btn-grd-primary"
              >
                <Copy size={14} /> Copy từ {prev}
              </button>
            )}
            {PRESETS.map((p) => (
              <button
                key={p.key}
                type="button"
                disabled={busy || buckets.length === 0}
                onClick={() => doCreatePreset(p.key)}
                className="btn btn-ghost"
                title={p.desc}
              >
                Dùng preset: {p.label}
              </button>
            ))}
            <button
              type="button"
              disabled={busy}
              onClick={doCreateEmpty}
              className="btn btn-ghost"
            >
              Tạo rỗng (chỉnh sau)
            </button>
          </div>
          {buckets.length === 0 && (
            <div className="muted text-sm">
              Chưa có bucket nào.{" "}
              <a href="/buckets" className="underline">
                Tạo bucket trước →
              </a>
            </div>
          )}
        </>
      )}

      {err && <div className="neg text-sm">{err}</div>}
    </div>
  );
}
