import { notFound } from "next/navigation";
import { PlanDetail } from "@/components/plans/PlanDetail";
import { api } from "@/lib/api";

type Plan = {
  id: number;
  month: string;
  expected_income: string;
  strategy: "soft" | "envelope" | "zero_based" | "pay_yourself_first";
  carry_over_enabled: boolean;
  note: string | null;
  allocations: {
    id: number;
    monthly_plan_id: number;
    bucket_id: number;
    method: "amount" | "percent";
    value: string;
    rollover: boolean;
    note: string | null;
  }[];
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
  strategy: Plan["strategy"];
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

export default async function PlanDetailPage({
  params,
}: {
  params: { month: string };
}) {
  const month = params.month;
  if (!/^\d{4}-\d{2}$/.test(month)) notFound();

  let plan: Plan;
  try {
    plan = await api<Plan>(`/plans/${month}`);
  } catch {
    notFound();
  }
  const [summary, buckets] = await Promise.all([
    api<Summary>(`/plans/${month}/summary`),
    api<Bucket[]>("/buckets"),
  ]);

  return (
    <PlanDetail
      month={month}
      plan={plan!}
      summary={summary}
      buckets={buckets.filter((b) => !b.archived)}
    />
  );
}
