import {
  ArrowDownRight,
  ArrowUpRight,
  Banknote,
  Minus,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { api, fmtVND } from "@/lib/api";
import { BreakdownList } from "@/components/dashboard/BreakdownList";
import { BreakdownPie } from "@/components/dashboard/BreakdownPie";
import { CashflowChart } from "@/components/dashboard/CashflowChart";
import { PeriodTabs } from "@/components/dashboard/PeriodTabs";
import { PlanProgressCard } from "@/components/dashboard/PlanProgressCard";

type Kpi = { label: string; value: string; currency: string; delta_pct: number | null };
type CF = { day: string; expense: string; income: string; net_cumulative: string };
type Bk = {
  category_id: number | null;
  category_name: string;
  total: string;
  pct: number;
  count: number;
};
type Mc = { name: string; total: string; count: number };

type Dashboard = {
  kpis: Kpi[];
  cashflow: CF[];
  breakdown: Bk[];
  top_merchants: Mc[];
};

type Props = { searchParams: Promise<{ period?: string }> };

const ALLOWED = ["week", "month", "year"] as const;
type Period = (typeof ALLOWED)[number];

export default async function Home({ searchParams }: Props) {
  const { period: raw } = await searchParams;
  const period: Period = (ALLOWED as readonly string[]).includes(raw || "")
    ? (raw as Period)
    : "month";

  let data: Dashboard | null = null;
  let err: string | null = null;
  try {
    data = await api<Dashboard>(`/dashboard/overview?period=${period}`);
  } catch (e) {
    err = (e as Error).message;
  }

  if (err) {
    return (
      <div className="card">
        <h1 className="text-xl font-bold mb-2">Dashboard</h1>
        <p className="text-red-400">API unreachable: {err}</p>
      </div>
    );
  }
  if (!data) return null;

  const bucket: "day" | "month" = period === "year" ? "month" : "day";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <PeriodTabs current={period} />
      </div>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {data.kpis.map((k, i) => {
          const iconByPos = [
            { Icon: Wallet, badge: "icon-badge-primary" },
            { Icon: TrendingDown, badge: "icon-badge-danger" },
            { Icon: TrendingUp, badge: "icon-badge-success" },
            { Icon: Banknote, badge: "icon-badge-info" },
          ][i % 4];
          const Icon = iconByPos.Icon;
          const delta = k.delta_pct;
          // For expense KPI (index 1), rising is bad. For others, rising is good.
          const positiveIsGood = i !== 1;
          const chipClass =
            delta == null
              ? "chip-muted"
              : delta === 0
                ? "chip-muted"
                : (delta > 0) === positiveIsGood
                  ? "chip-success"
                  : "chip-danger";
          const DeltaIcon =
            delta == null || delta === 0
              ? Minus
              : delta > 0
                ? ArrowUpRight
                : ArrowDownRight;
          return (
            <div key={k.label} className="card">
              <div className="flex items-start justify-between mb-3">
                <span className={`icon-badge ${iconByPos.badge}`}>
                  <Icon size={18} strokeWidth={2.25} />
                </span>
                {delta !== null && delta !== undefined && (
                  <span className={`chip ${chipClass}`}>
                    <DeltaIcon size={11} strokeWidth={2.5} />
                    {Math.abs(delta).toFixed(1)}%
                  </span>
                )}
              </div>
              <div className="text-2xl font-semibold tracking-tight">
                {fmtVND(k.value)}
              </div>
              <div className="muted text-xs mt-1">{k.label}</div>
            </div>
          );
        })}
      </section>

      <PlanProgressCard />

      <section className="grid md:grid-cols-2 gap-4">
        <div className="card">
          <div className="flex justify-between items-baseline mb-2">
            <h2 className="font-semibold">Biểu đồ thu / chi</h2>
            <span className="muted text-xs">
              {period === "week" ? "7 ngày" : period === "month" ? "trong tháng" : "12 tháng"}
            </span>
          </div>
          <CashflowChart data={data.cashflow} bucket={bucket} />
        </div>

        <div className="card">
          <div className="flex justify-between items-baseline mb-2">
            <h2 className="font-semibold">Chi theo category</h2>
            <span className="muted text-xs">click để xem detail</span>
          </div>
          <BreakdownPie data={data.breakdown} period={period} />
        </div>
      </section>

      <section className="card">
        <div className="flex justify-between items-baseline mb-2">
          <h2 className="font-semibold">Chi tiết theo category</h2>
          <span className="muted text-xs">{data.breakdown.length} category</span>
        </div>
        <BreakdownList data={data.breakdown} period={period} />
      </section>

      <section className="card">
        <h2 className="font-semibold mb-3">Top merchant</h2>
        {data.top_merchants.length === 0 ? (
          <p className="muted text-sm">Chưa có merchant nào trong kỳ.</p>
        ) : (
          <ul>
            {data.top_merchants.map((m) => (
              <li key={m.name} className="flex justify-between text-sm py-1">
                <span>{m.name}</span>
                <span className="font-mono">
                  {fmtVND(m.total)} · {m.count} lần
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
