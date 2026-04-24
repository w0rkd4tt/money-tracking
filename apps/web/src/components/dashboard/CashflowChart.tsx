"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Point = { day: string; expense: string; income: string; net_cumulative: string };

const fmt = (n: number) =>
  n >= 1_000_000
    ? (n / 1_000_000).toFixed(1) + "M"
    : n >= 1_000
    ? (n / 1_000).toFixed(0) + "k"
    : String(n);

export function CashflowChart({ data, bucket }: { data: Point[]; bucket: "day" | "month" }) {
  const rows = data.map((p) => ({
    label:
      bucket === "month"
        ? new Date(p.day).toLocaleString("vi-VN", { month: "short" })
        : new Date(p.day).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" }),
    Chi: Number(p.expense),
    Thu: Number(p.income),
    Net: Number(p.net_cumulative),
  }));

  return (
    <div style={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="cf-income" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity={0.9} />
              <stop offset="100%" stopColor="#10b981" stopOpacity={0.5} />
            </linearGradient>
            <linearGradient id="cf-expense" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ef4444" stopOpacity={0.9} />
              <stop offset="100%" stopColor="#ef4444" stopOpacity={0.5} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#2b2f38" vertical={false} />
          <XAxis
            dataKey="label"
            stroke="#9097a4"
            fontSize={11}
            tickLine={false}
            axisLine={{ stroke: "#2b2f38" }}
          />
          <YAxis
            stroke="#9097a4"
            fontSize={11}
            tickFormatter={fmt}
            tickLine={false}
            axisLine={false}
          />
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
            labelStyle={{ color: "#9097a4", marginBottom: 4 }}
            formatter={(v: number) =>
              new Intl.NumberFormat("vi-VN").format(v) + " ₫"
            }
          />
          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            iconType="circle"
            iconSize={8}
          />
          <Line
            type="monotone"
            dataKey="Chi"
            stroke="url(#cf-expense)"
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 5, stroke: "#ef4444", strokeWidth: 2, fill: "#1e2128" }}
          />
          <Line
            type="monotone"
            dataKey="Thu"
            stroke="url(#cf-income)"
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 5, stroke: "#10b981", strokeWidth: 2, fill: "#1e2128" }}
          />
          <Line
            type="monotone"
            dataKey="Net"
            stroke="#2196f3"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            dot={false}
            activeDot={{ r: 4, stroke: "#2196f3", strokeWidth: 2, fill: "#1e2128" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
