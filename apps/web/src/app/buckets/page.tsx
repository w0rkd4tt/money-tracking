import { BucketsManager } from "@/components/buckets/BucketsManager";
import { api } from "@/lib/api";

type Bucket = {
  id: number;
  name: string;
  icon: string | null;
  color: string | null;
  sort_order: number;
  archived: boolean;
  note: string | null;
  category_ids: number[];
};

type Category = {
  id: number;
  name: string;
  kind: "expense" | "income" | "transfer";
  path: string;
};

export default async function BucketsPage() {
  const [buckets, categories] = await Promise.all([
    api<Bucket[]>("/buckets?include_archived=true"),
    api<Category[]>("/categories"),
  ]);
  const expenseCats = categories.filter((c) => c.kind === "expense");
  return <BucketsManager initialBuckets={buckets} categories={expenseCats} />;
}
