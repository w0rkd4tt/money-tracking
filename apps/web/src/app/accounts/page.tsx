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

export default async function AccountsPage() {
  const [accounts, balances] = await Promise.all([
    api<Account[]>("/accounts?include_archived=true"),
    api<Balance[]>("/accounts/balance"),
  ]);

  return <AccountsManager initialAccounts={accounts} initialBalances={balances} />;
}
