import { TransactionFilters } from "@/components/transactions/TransactionFilters";
import { TransactionsManager } from "@/components/transactions/TransactionsManager";
import { api } from "@/lib/api";

type Tx = {
  id: number;
  ts: string;
  amount: string;
  currency: string;
  account_id: number;
  category_id: number | null;
  merchant_text: string | null;
  note: string | null;
  source: string;
  status: string;
  transfer_group_id: number | null;
};

type Paginated<T> = {
  items: T[];
  total: number;
  page: number;
  size: number;
  has_next: boolean;
};

type Account = {
  id: number;
  name: string;
  type: string;
  currency: string;
  archived: boolean;
  icon?: string | null;
};
type Category = {
  id: number;
  name: string;
  path: string;
  kind: "expense" | "income" | "transfer";
};

type Props = {
  searchParams: Promise<{
    account_id?: string;
    category_id?: string;
    status?: string;
    q?: string;
    from?: string;
    to?: string;
    sort?: string;
    order?: string;
  }>;
};

export default async function TransactionsPage({ searchParams }: Props) {
  const sp = await searchParams;
  const params = new URLSearchParams();
  params.set("size", "100");
  if (sp.account_id) params.set("account_id", sp.account_id);
  if (sp.category_id) params.set("category_id", sp.category_id);
  if (sp.status) params.set("status", sp.status);
  if (sp.q) params.set("q", sp.q);
  if (sp.from) params.set("from", sp.from);
  if (sp.to) params.set("to", sp.to);
  if (sp.sort) params.set("sort", sp.sort);
  if (sp.order) params.set("order", sp.order);

  const [txs, accounts, categories] = await Promise.all([
    api<Paginated<Tx>>(`/transactions?${params.toString()}`),
    api<Account[]>("/accounts"),
    api<Category[]>("/categories"),
  ]);
  const accMap = Object.fromEntries(accounts.map((a) => [a.id, a.name]));
  const catMap = Object.fromEntries(categories.map((c) => [c.id, c.path]));

  return (
    <div className="space-y-4">
      <TransactionFilters accounts={accounts} categories={categories} />
      <TransactionsManager
        initialTxs={txs.items}
        total={txs.total}
        accounts={accounts}
        categories={categories}
        accMap={accMap}
        catMap={catMap}
      />
    </div>
  );
}
