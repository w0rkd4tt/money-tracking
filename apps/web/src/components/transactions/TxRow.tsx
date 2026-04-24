import { fmtVND, fmtDate } from "@/lib/api";

const SOURCE_ICON: Record<string, string> = {
  manual: "✋",
  chat_web: "💬",
  chat_telegram: "🤖",
  gmail: "📧",
  agent_propose: "🧠",
};

function sourceLabel(source: string): string {
  if (source.startsWith("gmail:")) {
    return `📧 ${source.slice(6)}`;
  }
  return `${SOURCE_ICON[source] || "•"} ${source}`;
}

type Tx = {
  id: number;
  ts: string;
  amount: string;
  account_id: number;
  merchant_text: string | null;
  note: string | null;
  source: string;
  status: string;
  transfer_group_id: number | null;
};

export function TxRow({
  tx,
  accountName,
  categoryName,
}: {
  tx: Tx;
  accountName: string;
  categoryName?: string | null;
}) {
  return (
    <tr className="border-b border-[var(--border)]">
      <td className="py-2 whitespace-nowrap">{fmtDate(tx.ts)}</td>
      <td>{accountName}</td>
      <td className="muted">{categoryName || "—"}</td>
      <td>
        {tx.merchant_text || tx.note || "—"}
        {tx.transfer_group_id ? " ⇄" : ""}
      </td>
      <td
        className={
          "text-right font-mono " + (Number(tx.amount) < 0 ? "neg" : "pos")
        }
      >
        {fmtVND(tx.amount)}
      </td>
      <td>{sourceLabel(tx.source)}</td>
      <td className="muted text-xs">{tx.status}</td>
    </tr>
  );
}
