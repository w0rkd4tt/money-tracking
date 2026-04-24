import Link from "next/link";
import { fmtVND } from "@/lib/api";

type Slice = {
  category_id: number | null;
  category_name: string;
  total: string;
  pct: number;
  count: number;
};

const PALETTE = [
  "#60a5fa",
  "#f472b6",
  "#34d399",
  "#fbbf24",
  "#c084fc",
  "#f87171",
  "#a78bfa",
  "#22d3ee",
  "#fb923c",
  "#4ade80",
];

export function BreakdownList({
  data,
  period,
}: {
  data: Slice[];
  period: string;
}) {
  if (data.length === 0) {
    return <p className="muted text-sm">Chưa có chi tiêu trong kỳ.</p>;
  }
  return (
    <ul className="divide-y divide-[var(--border)]">
      {data.map((s, i) => {
        const inner = (
          <div className="flex items-center justify-between py-2 text-sm hover:bg-[var(--border)] -mx-2 px-2 rounded transition">
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ background: PALETTE[i % PALETTE.length] }}
              />
              <span className="truncate">{s.category_name}</span>
              <span className="muted text-xs">({s.count})</span>
            </div>
            <div className="flex items-center gap-3 font-mono">
              <span>{fmtVND(s.total)}</span>
              <span className="muted text-xs w-12 text-right">
                {s.pct.toFixed(1)}%
              </span>
            </div>
          </div>
        );
        return (
          <li key={s.category_id ?? i}>
            {s.category_id ? (
              <Link
                href={`/categories/${s.category_id}?period=${period}`}
                className="block"
              >
                {inner}
              </Link>
            ) : (
              inner
            )}
          </li>
        );
      })}
    </ul>
  );
}
