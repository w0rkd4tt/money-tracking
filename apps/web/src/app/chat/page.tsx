import { ChatPanel } from "@/components/chat/ChatPanel";
import { api } from "@/lib/api";

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

export default async function ChatPage() {
  // Pre-fetch accounts + categories so the inline manual-fallback form is ready
  // even when LLM is unreachable.
  const [accounts, categories] = await Promise.all([
    api<Account[]>("/accounts"),
    api<Category[]>("/categories"),
  ]);
  return <ChatPanel accounts={accounts} categories={categories} />;
}
