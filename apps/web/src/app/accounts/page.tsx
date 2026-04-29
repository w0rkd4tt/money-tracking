import { api } from "@/lib/api";
import { AccountsManager } from "@/components/accounts/AccountsManager";

type Account = {
  id: number;
  name: string;
  type: string;
  currency: string;
  opening_balance: string;
  icon: string | null;
  color: string | null;
  is_default: boolean;
  archived: boolean;
  credit_limit: string | null;
  statement_close_day: number | null;
};

type Balance = {
  account_id: number;
  name: string;
  type: string;
  currency: string;
  balance: string;
  credit_limit: string | null;
  debt: string | null;
  available_credit: string | null;
  utilization_pct: number | null;
};

type Bucket = {
  id: number;
  name: string;
  icon: string | null;
  color: string | null;
  account_ids: number[];
};

export default async function AccountsPage() {
  const [accounts, balances, buckets] = await Promise.all([
    api<Account[]>("/accounts?include_archived=true"),
    api<Balance[]>("/accounts/balance"),
    api<Bucket[]>("/buckets"),
  ]);

  // Pre-compute account_id → bucket so the client component just looks it up.
  const accountToBucket = new Map<number, { name: string; icon: string | null; color: string | null }>();
  for (const b of buckets) {
    for (const aid of b.account_ids) {
      accountToBucket.set(aid, { name: b.name, icon: b.icon, color: b.color });
    }
  }
  const bucketByAccount = Object.fromEntries(accountToBucket.entries());

  return (
    <AccountsManager
      initialAccounts={accounts}
      initialBalances={balances}
      bucketByAccount={bucketByAccount}
    />
  );
}
