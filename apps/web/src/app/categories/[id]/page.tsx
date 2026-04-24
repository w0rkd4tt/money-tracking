import Link from "next/link";

import { api, fmtDate, fmtVND } from "@/lib/api";
import { CashflowChart } from "@/components/dashboard/CashflowChart";
import { PeriodTabs } from "@/components/dashboard/PeriodTabs";

type CategoryOut = {
  id: number;
  name: string;
  kind: string;
  parent_id: number | null;
  icon: string | null;
  color: string | null;
  path: string;
};

type CashflowPoint = {
  day: string;
  expense: string;
  income: string;
  net_cumulative: string;
};

type MerchantStat = { merchant_id: number | null; name: string; total: string; count: number };

type Tx = {
  id: number;
  ts: string;
  amount: string;
  currency: string;
  account_id: number;
  merchant_text: string | null;
  note: string | null;
  source: string;
  status: string;
};

type Stats = {
  category: CategoryOut;
  period: string;
  start: string;
  end: string;
  total: string;
  count: number;
  avg_per_tx: string;
  cashflow: CashflowPoint[];
  top_merchants: MerchantStat[];
  transactions: Tx[];
};

type Account = { id: number; name: string };

const ALLOWED = ["week", "month", "year"] as const;
type Period = (typeof ALLOWED)[number];

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ period?: string }>;
};

export default async function CategoryDetail({ params, searchParams }: Props) {
  const { id } = await params;
  const { period: raw } = await searchParams;
  const period: Period = (ALLOWED as readonly string[]).includes(raw || "")
    ? (raw as Period)
    : "month";

  let stats: Stats | null = null;
  let accounts: Account[] = [];
  let err: string | null = null;
  try {
    [stats, accounts] = await Promise.all([
      api<Stats>(`/categories/${id}/stats?period=${period}`),
      api<Account[]>("/accounts"),
    ]);
  } catch (e) {
    err = (e as Error).message;
  }

  if (err || !stats) {
    return (
      <div className="card">
        <p className="text-red-400">Không tải được category: {err}</p>
        <Link href="/" className="text-blue-400 hover:underline">
          ← Dashboard
        </Link>
      </div>
    );
  }

  const accMap = Object.fromEntries(accounts.map((a) => [a.id, a.name]));
  const bucket: "day" | "month" = period === "year" ? "month" : "day";
  const color = stats.category.color || "#60a5fa";

  const daysInPeriod = Math.max(
    1,
    Math.ceil(
      (new Date(stats.end).getTime() - new Date(stats.start).getTime()) / 86400000
    )
  );
  const perDay = Number(stats.total) / daysInPeriod;

  return (
    <div className="space-y-6">
      <div className="text-sm muted">
        <Link href="/" className="hover:underline">
          Dashboard
        </Link>{" "}
        /{" "}
        <Link href={`/?period=${period}`} className="hover:underline">
          Kỳ {period}
        </Link>{" "}
        / Category
      </div>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <span
            className="text-3xl w-12 h-12 rounded-full flex items-center justify-center"
            style={{ background: color + "22" }}
          >
            {stats.category.icon || "📁"}
          </span>
          <div>
            <h1 className="text-2xl font-bold">{stats.category.path}</h1>
            <p className="muted text-xs uppercase tracking-wider">
              {stats.category.kind}
              {" · "}
              {stats.start} → {stats.end}
            </p>
          </div>
        </div>
        <PeriodTabs current={period} />
      </div>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card">
          <div className="muted text-xs uppercase">Tổng</div>
          <div className="text-2xl font-semibold mt-1">{fmtVND(stats.total)}</div>
        </div>
        <div className="card">
          <div className="muted text-xs uppercase">Số giao dịch</div>
          <div className="text-2xl font-semibold mt-1">{stats.count}</div>
        </div>
        <div className="card">
          <div className="muted text-xs uppercase">TB/giao dịch</div>
          <div className="text-2xl font-semibold mt-1">{fmtVND(stats.avg_per_tx)}</div>
        </div>
        <div className="card">
          <div className="muted text-xs uppercase">TB/ngày</div>
          <div className="text-2xl font-semibold mt-1">{fmtVND(perDay)}</div>
        </div>
      </section>

      <section className="card">
        <div className="flex justify-between items-baseline mb-2">
          <h2 className="font-semibold">Biểu đồ chi tiêu — {stats.category.path}</h2>
          <span className="muted text-xs">
            {period === "week" ? "7 ngày" : period === "month" ? "trong tháng" : "12 tháng"}
          </span>
        </div>
        <CashflowChart data={stats.cashflow} bucket={bucket} />
      </section>

      <section className="grid md:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="font-semibold mb-3">Top merchants</h2>
          {stats.top_merchants.length === 0 ? (
            <p className="muted text-sm">Chưa có merchant nào trong kỳ.</p>
          ) : (
            <ul>
              {stats.top_merchants.map((m) => (
                <li key={m.name} className="flex justify-between text-sm py-1">
                  <span>{m.name}</span>
                  <span className="font-mono">
                    {fmtVND(m.total)} · {m.count} lần
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="card">
          <h2 className="font-semibold mb-3">Phân bố theo ngày (raw)</h2>
          <div className="max-h-[260px] overflow-auto text-xs">
            <table className="w-full">
              <tbody>
                {stats.cashflow
                  .filter((p) => Number(p.expense) > 0)
                  .slice(-30)
                  .reverse()
                  .map((p) => (
                    <tr key={p.day} className="border-b border-[var(--border)]">
                      <td className="py-1">
                        {bucket === "month"
                          ? new Date(p.day).toLocaleString("vi-VN", {
                              month: "short",
                              year: "numeric",
                            })
                          : new Date(p.day).toLocaleDateString("vi-VN")}
                      </td>
                      <td className="text-right font-mono neg">{fmtVND(p.expense)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="card">
        <h2 className="font-semibold mb-3">
          Giao dịch ({stats.transactions.length}
          {stats.count > stats.transactions.length ? `/${stats.count}` : ""})
        </h2>
        {stats.transactions.length === 0 ? (
          <p className="muted text-sm">Chưa có giao dịch nào trong kỳ.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="muted text-left border-b border-[var(--border)]">
                <th className="pb-2">Thời gian</th>
                <th>Tài khoản</th>
                <th>Merchant / ghi chú</th>
                <th className="text-right">Số tiền</th>
                <th>Nguồn</th>
              </tr>
            </thead>
            <tbody>
              {stats.transactions.map((t) => (
                <tr key={t.id} className="border-b border-[var(--border)]">
                  <td className="py-2 whitespace-nowrap">{fmtDate(t.ts)}</td>
                  <td>{accMap[t.account_id] || t.account_id}</td>
                  <td>{t.merchant_text || t.note || "—"}</td>
                  <td
                    className={
                      "text-right font-mono " + (Number(t.amount) < 0 ? "neg" : "pos")
                    }
                  >
                    {fmtVND(t.amount)}
                  </td>
                  <td>{t.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
