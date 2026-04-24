import { api } from "@/lib/api";
import { TransfersManager } from "@/components/transfers/TransfersManager";

type TG = {
  id: number;
  ts: string;
  from_account_id: number;
  to_account_id: number;
  amount: string;
  fee: string;
  currency: string;
  fx_rate: string | null;
  note: string | null;
  source: string;
  transaction_ids: number[];
};

type Account = {
  id: number;
  name: string;
  type: string;
  currency: string;
  icon: string | null;
  archived: boolean;
};

export default async function TransfersPage() {
  const [transfers, accounts] = await Promise.all([
    api<TG[]>("/transfers"),
    api<Account[]>("/accounts"),
  ]);

  return <TransfersManager initialAccounts={accounts} initialTransfers={transfers} />;
}
