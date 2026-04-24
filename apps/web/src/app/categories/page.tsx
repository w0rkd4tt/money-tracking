import { api } from "@/lib/api";
import { CategoriesTreeDashboard } from "@/components/categories/CategoriesTreeDashboard";

type CategoryStatRow = {
  id: number;
  name: string;
  parent_id: number | null;
  path: string;
  kind: string;
  icon: string | null;
  color: string | null;
  total: number;
  count: number;
};

type Props = { searchParams: Promise<{ period?: string }> };

const ALLOWED = ["week", "month", "year"] as const;
type Period = (typeof ALLOWED)[number];

export default async function CategoriesPage({ searchParams }: Props) {
  const { period: raw } = await searchParams;
  const period: Period = (ALLOWED as readonly string[]).includes(raw || "")
    ? (raw as Period)
    : "month";

  const rows = await api<CategoryStatRow[]>(
    `/categories/stats/all?period=${period}&kind=all`
  );
  return <CategoriesTreeDashboard initialRows={rows} period={period} />;
}
