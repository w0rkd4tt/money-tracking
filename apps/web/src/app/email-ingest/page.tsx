import { api } from "@/lib/api";
import { EmailIngestDashboard } from "@/components/email-ingest/EmailIngestDashboard";

type IngestedItem = {
  transaction_id: number;
  ts: string;
  amount: string;
  currency: string;
  status: string;
  confidence: number;
  account_id: number;
  account_name: string | null;
  category_id: number | null;
  category_name: string | null;
  merchant: string | null;
  note: string | null;
  rule_name: string | null;
  sender: string | null;
  subject: string | null;
  message_id: string | null;
  is_llm_fallback: boolean;
};

type Category = {
  id: number;
  name: string;
  path: string;
  kind: "expense" | "income" | "transfer";
};

type Stats = {
  total: number;
  by_rule: Record<string, number>;
  by_status: Record<string, number>;
  by_confidence: Record<string, number>;
  llm_fallback_count: number;
  rule_count: number;
};

export default async function EmailIngestPage() {
  const [items, stats, categories] = await Promise.all([
    api<IngestedItem[]>("/gmail/ingested?limit=200"),
    api<Stats>("/gmail/ingest-stats"),
    api<Category[]>("/categories"),
  ]);

  return (
    <EmailIngestDashboard
      initialItems={items}
      initialStats={stats}
      categories={categories}
    />
  );
}
