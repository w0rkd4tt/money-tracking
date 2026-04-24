import Link from "next/link";
import { PlansCreatePanel } from "@/components/plans/PlansCreatePanel";
import { api, fmtVND } from "@/lib/api";

type Plan = {
  id: number;
  month: string;
  expected_income: string;
  strategy: "soft" | "envelope" | "zero_based" | "pay_yourself_first";
  carry_over_enabled: boolean;
  note: string | null;
  allocations: { id: number; bucket_id: number; method: string; value: string }[];
};

type Bucket = { id: number; name: string; archived: boolean };

const STRATEGY_LABEL: Record<Plan["strategy"], string> = {
  soft: "Hướng dẫn nhẹ",
  envelope: "Nghiêm ngặt (envelope)",
  zero_based: "Zero-based",
  pay_yourself_first: "Pay-yourself-first",
};

function fmtMonth(m: string): string {
  const d = new Date(m);
  return d.toLocaleDateString("vi-VN", { month: "2-digit", year: "numeric" });
}

export default async function PlansPage() {
  const [plans, buckets] = await Promise.all([
    api<Plan[]>("/plans"),
    api<Bucket[]>("/buckets"),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">📋 Kế hoạch tháng</h1>
        <p className="muted text-sm">
          Phân bổ thu nhập vào các nhóm mỗi tháng. Theo dõi quota, cảnh báo khi gần/vượt.
        </p>
      </div>

      <PlansCreatePanel
        buckets={buckets.filter((b) => !b.archived)}
        existingMonths={plans.map((p) => p.month)}
      />

      <div>
        <h2 className="text-base font-semibold mb-2">Các kế hoạch đã lập</h2>
        {plans.length === 0 ? (
          <div className="card muted text-sm">
            Chưa có kế hoạch nào. Tạo kế hoạch đầu tiên ở khung bên trên.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {plans.map((p) => {
              const monthKey = p.month.slice(0, 7); // YYYY-MM
              return (
                <Link
                  key={p.id}
                  href={`/plans/${monthKey}`}
                  className="card hover:border-blue-500 transition-colors flex flex-col gap-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-lg font-semibold">{fmtMonth(p.month)}</span>
                    <span className="text-xs muted">{STRATEGY_LABEL[p.strategy]}</span>
                  </div>
                  <div className="text-sm">
                    <span className="muted">Thu nhập dự kiến: </span>
                    <span className="font-medium">{fmtVND(p.expected_income)}</span>
                  </div>
                  <div className="text-sm muted">
                    {p.allocations.length} nhóm phân bổ ·{" "}
                    {p.carry_over_enabled ? "rollover ON" : "rollover OFF"}
                  </div>
                  {p.note && <div className="text-xs muted italic truncate">{p.note}</div>}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
