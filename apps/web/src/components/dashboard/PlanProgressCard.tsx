import Link from "next/link";
import { api, fmtVND } from "@/lib/api";

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
  strategy: string;
  expected_income: string;
  actual_income: string;
  total_allocated: string;
  total_spent: string;
  unplanned_spent: string;
  buckets: BucketStatus[];
};

type Bucket = {
  id: number;
  icon: string | null;
  color: string | null;
  archived: boolean;
};

function currentYearMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function statusBarColor(s: BucketStatus["status"]): string {
  return s === "over"
    ? "bg-red-600"
    : s === "warn"
      ? "bg-amber-500"
      : s === "unplanned"
        ? "bg-slate-600"
        : "bg-emerald-600";
}

function fmtMonthLong(ym: string): string {
  const [y, m] = ym.split("-");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString("vi-VN", {
    month: "long",
    year: "numeric",
  });
}

export async function PlanProgressCard() {
  const month = currentYearMonth();

  // Summary always succeeds (returns zero buckets if no plan).
  // Fetch /plans/{month} separately to detect plan existence; 404 tolerated.
  let summary: Summary | null = null;
  let planExists = false;
  let buckets: Bucket[] = [];
  try {
    [summary, buckets] = await Promise.all([
      api<Summary>(`/plans/${month}/summary`),
      api<Bucket[]>("/buckets"),
    ]);
    // Probe plan existence
    try {
      await api<unknown>(`/plans/${month}`);
      planExists = true;
    } catch {
      planExists = false;
    }
  } catch (e) {
    return (
      <section className="card">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">📋 Kế hoạch tháng</h2>
        </div>
        <p className="muted text-sm mt-2">
          Không tải được kế hoạch: {(e as Error).message}
        </p>
      </section>
    );
  }

  if (!summary) return null;

  const bucketMeta = new Map(buckets.map((b) => [b.id, b]));
  const expected = Number(summary.expected_income);
  const actual = Number(summary.actual_income);
  const allocated = Number(summary.total_allocated);
  const spent = Number(summary.total_spent);
  const unplanned = Number(summary.unplanned_spent);

  // Overall spent-of-allocated bar
  const overallPct = allocated > 0 ? Math.min(100, (spent / allocated) * 100) : 0;
  const overallColor =
    allocated > 0 && spent > allocated
      ? "bg-red-600"
      : allocated > 0 && spent / allocated >= 0.8
        ? "bg-amber-500"
        : "bg-emerald-600";

  return (
    <section className="card">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <h2 className="font-semibold">
          📋 Tiến độ kế hoạch · {fmtMonthLong(month)}
        </h2>
        {planExists ? (
          <Link
            href={`/plans/${month}`}
            className="text-xs muted hover:underline"
          >
            Xem chi tiết →
          </Link>
        ) : (
          <Link
            href="/plans"
            className="btn btn-grd-primary !text-xs !py-1"
          >
            + Lập kế hoạch
          </Link>
        )}
      </div>

      {!planExists ? (
        <div className="muted text-sm">
          Chưa có kế hoạch cho tháng này. Lập kế hoạch để phân bổ thu nhập vào
          các nhóm và theo dõi quota ngay trên dashboard.
        </div>
      ) : (
        <>
          {/* mini KPI row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-sm">
            <div>
              <div className="muted text-xs">Thu dự kiến</div>
              <div className="font-medium">{fmtVND(summary.expected_income)}</div>
            </div>
            <div>
              <div className="muted text-xs">Thu thực tế</div>
              <div className="font-medium">
                {fmtVND(summary.actual_income)}
                {expected > 0 && (
                  <span
                    className={`ml-1 text-xs ${actual >= expected ? "pos" : "neg"}`}
                  >
                    ({actual >= expected ? "+" : ""}
                    {(((actual - expected) / expected) * 100).toFixed(0)}%)
                  </span>
                )}
              </div>
            </div>
            <div>
              <div className="muted text-xs">Đã phân bổ</div>
              <div className="font-medium">{fmtVND(summary.total_allocated)}</div>
            </div>
            <div>
              <div className="muted text-xs">Đã chi</div>
              <div className="font-medium">
                {fmtVND(summary.total_spent)}
                {allocated > 0 && (
                  <span
                    className={`ml-1 text-xs ${
                      spent > allocated ? "neg" : "muted"
                    }`}
                  >
                    ({((spent / allocated) * 100).toFixed(0)}%)
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* overall bar */}
          {allocated > 0 && (
            <div className="mb-3">
              <div className="h-2 bg-[var(--border)] rounded overflow-hidden">
                <div
                  className={`h-full ${overallColor}`}
                  style={{ width: `${overallPct}%` }}
                />
              </div>
              <div className="flex justify-between text-xs muted mt-1">
                <span>
                  tổng quota còn{" "}
                  <span className={spent > allocated ? "neg" : ""}>
                    {fmtVND(Math.max(0, allocated - spent))}
                  </span>
                </span>
                {unplanned > 0 && (
                  <span className="neg">
                    {fmtVND(unplanned)} chưa thuộc bucket
                  </span>
                )}
              </div>
            </div>
          )}

          {/* per-bucket bars */}
          {summary.buckets.length === 0 ? (
            <div className="muted text-sm">Chưa có bucket nào được gán.</div>
          ) : (
            <div className="flex flex-col gap-2">
              {summary.buckets.map((b) => {
                const meta = bucketMeta.get(b.bucket_id);
                const pctClamped = Math.min(100, b.pct);
                return (
                  <div key={b.bucket_id} className="flex flex-col gap-0.5">
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span
                          className="w-5 h-5 flex items-center justify-center rounded-full text-xs shrink-0"
                          style={{ backgroundColor: meta?.color || "#1f2937" }}
                        >
                          {meta?.icon || "🪣"}
                        </span>
                        <span className="truncate">{b.bucket_name}</span>
                        {b.status === "unplanned" && (
                          <span className="text-xs muted">(chưa phân bổ)</span>
                        )}
                      </div>
                      <div className="text-xs shrink-0 font-mono">
                        <span
                          className={
                            b.status === "over"
                              ? "neg"
                              : b.status === "warn"
                                ? "text-amber-400"
                                : ""
                          }
                        >
                          {fmtVND(b.spent)}
                        </span>
                        <span className="muted"> / {fmtVND(b.allocated)}</span>
                      </div>
                    </div>
                    <div className="h-1.5 bg-[var(--border)] rounded overflow-hidden">
                      <div
                        className={`h-full ${statusBarColor(b.status)}`}
                        style={{ width: `${pctClamped}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </section>
  );
}
