"use client";

import { useRouter } from "next/navigation";
import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

type Slice = {
  category_id: number | null;
  category_name: string;
  total: string;
  pct: number;
  count: number;
};

const PALETTE = [
  "#2196f3", // brand blue
  "#10b981", // success green
  "#f59e0b", // warning amber
  "#ef4444", // danger red
  "#06b6d4", // info cyan
  "#a855f7", // purple
  "#ec4899", // pink
  "#14b8a6", // teal
  "#f97316", // orange
  "#6366f1", // indigo
];

export function BreakdownPie({ data, period }: { data: Slice[]; period: string }) {
  const router = useRouter();

  if (data.length === 0) {
    return <p className="muted text-sm">Chưa có chi tiêu trong kỳ.</p>;
  }

  const rows = data.map((s, i) => ({
    id: s.category_id,
    name: s.category_name,
    value: Number(s.total),
    count: s.count,
    pct: s.pct,
    color: PALETTE[i % PALETTE.length],
  }));

  const goDetail = (id: number | null) => {
    if (id) router.push(`/categories/${id}?period=${period}`);
  };

  return (
    <div style={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={rows}
            dataKey="value"
            nameKey="name"
            outerRadius={110}
            innerRadius={60}
            paddingAngle={2}
            stroke="#1e2128"
            strokeWidth={2}
            cursor="pointer"
            onClick={(_, idx) => goDetail(rows[idx]?.id ?? null)}
          >
            {rows.map((r, i) => (
              <Cell key={i} fill={r.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: "#1e2128",
              border: "1px solid #3a3f4b",
              borderRadius: 10,
              color: "#e7e9ee",
              fontSize: 12,
              padding: "8px 12px",
            }}
            itemStyle={{ color: "#e7e9ee" }}
            labelStyle={{ color: "#9097a4" }}
            formatter={(v: number, _name, p) => [
              new Intl.NumberFormat("vi-VN").format(v) + " ₫",
              `${p.payload.name} · ${p.payload.count} lần · ${p.payload.pct.toFixed(1)}%`,
            ]}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            formatter={(val) => <span style={{ color: "#e7e9ee" }}>{val}</span>}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
