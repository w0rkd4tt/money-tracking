"use client";

import { AlertTriangle, RefreshCw, Settings as SettingsIcon } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ExtractedTxCard, type Extracted } from "@/components/chat/ExtractedTxCard";
import { TransactionForm } from "@/components/transactions/TransactionForm";

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

type ChatResp = {
  intent: string;
  transactions: Extracted[];
  reply_text: string;
  provider: string;
};

type Turn =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; items: Extracted[] };

type LlmState = "unknown" | "ok" | "unreachable";

type HealthResp = {
  db: string;
  llm: "ok" | "unreachable";
  llm_provider?: string;
};

type ProviderOption = {
  id: string;
  name: string;
  enabled: boolean;
  is_default: boolean;
};

async function fetchHealth(): Promise<HealthResp | null> {
  try {
    const r = await fetch("/api/v1/health", { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as HealthResp;
  } catch {
    return null;
  }
}

type ProviderTest = { ok: boolean; detail: string };

export function ChatPanel({
  accounts,
  categories,
}: {
  accounts: Account[];
  categories: Category[];
}) {
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);
  const [llm, setLlm] = useState<LlmState>("unknown");
  const [llmProvider, setLlmProvider] = useState<string>("default");
  const [showFallback, setShowFallback] = useState(false);
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  // When a non-default provider is picked, we test IT (not the default) so the
  // UI gating below reflects the provider the user is actually about to use.
  const [providerStatus, setProviderStatus] = useState<ProviderTest | null>(null);
  const [testingSelected, setTestingSelected] = useState(false);

  const refreshHealth = useCallback(async () => {
    const h = await fetchHealth();
    if (!h) {
      setLlm("unreachable");
      return;
    }
    setLlm(h.llm === "ok" ? "ok" : "unreachable");
    if (h.llm_provider) setLlmProvider(h.llm_provider);
  }, []);

  const loadProviders = useCallback(async () => {
    try {
      const r = await fetch("/api/v1/llm/providers", { cache: "no-store" });
      if (!r.ok) return;
      const data = (await r.json()) as ProviderOption[];
      setProviders(data);
    } catch {
      // keep existing
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    loadProviders();
    const onFocus = () => {
      refreshHealth();
      loadProviders();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshHealth, loadProviders]);

  // When user picks a specific provider, test it so the input/send button
  // unblocks based on THAT provider's reachability (not the default's).
  useEffect(() => {
    if (!selectedProvider) {
      setProviderStatus(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setTestingSelected(true);
      try {
        const r = await fetch(
          `/api/v1/llm/providers/${encodeURIComponent(selectedProvider)}/test`,
          { method: "POST", cache: "no-store" }
        );
        if (!r.ok) throw new Error(await r.text());
        const data = (await r.json()) as ProviderTest;
        if (!cancelled) setProviderStatus({ ok: data.ok, detail: data.detail });
      } catch {
        if (!cancelled) setProviderStatus({ ok: false, detail: "error" });
      } finally {
        if (!cancelled) setTestingSelected(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedProvider]);

  const send = async () => {
    const t = text.trim();
    if (!t) return;
    setTurns((x) => [...x, { role: "user", text: t }]);
    setText("");
    setLoading(true);
    try {
      const r = await fetch("/api/v1/chat/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel: "web",
          external_id: "web-default",
          text: t,
          provider: selectedProvider || undefined,
        }),
      });
      if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
      const data: ChatResp = await r.json();
      setTurns((x) => [
        ...x,
        { role: "assistant", text: data.reply_text, items: data.transactions || [] },
      ]);
    } catch (e) {
      setTurns((x) => [
        ...x,
        { role: "assistant", text: "Lỗi: " + (e as Error).message, items: [] },
      ]);
      // Re-test whatever the user has picked so the banner updates.
      if (selectedProvider) {
        try {
          const r = await fetch(
            `/api/v1/llm/providers/${encodeURIComponent(selectedProvider)}/test`,
            { method: "POST", cache: "no-store" }
          );
          if (r.ok) {
            const data = (await r.json()) as ProviderTest;
            setProviderStatus({ ok: data.ok, detail: data.detail });
          }
        } catch {
          setProviderStatus({ ok: false, detail: "error" });
        }
      } else {
        refreshHealth();
      }
    } finally {
      setLoading(false);
    }
  };

  // ExtractedTxCard now handles confirm/reject/patch per-transaction with
  // inline dropdowns for account/category overrides.

  // Gate the UI only when the DEFAULT provider is down AND user hasn't picked
  // an alternative. If user has explicitly selected a provider, trust their
  // choice — even if the 30s ping timed out (some endpoints are slow to ping
  // but fine for real chat). A failed send will surface the real error inline.
  const llmDown = !selectedProvider && llm === "unreachable";
  const selectedUnreachable =
    selectedProvider && providerStatus && !providerStatus.ok;

  useEffect(() => {
    if (llmDown) setShowFallback(true);
  }, [llmDown]);

  return (
    <div className="max-w-3xl mx-auto flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-xl font-bold">Chat</h1>
        <div className="flex items-center gap-2 text-xs flex-wrap">
          <select
            value={selectedProvider}
            onChange={(e) => setSelectedProvider(e.target.value)}
            className="field !py-1 text-xs min-w-[180px]"
            title="Chọn provider cho phiên chat"
          >
            <option value="">Default ({llmProvider})</option>
            {providers
              .filter((p) => p.enabled)
              .map((p) => (
                <option key={p.id} value={p.name}>
                  {p.name}
                  {p.is_default ? " ★" : ""}
                </option>
              ))}
          </select>
          <Link
            href="/providers"
            className="btn btn-ghost !py-1 !px-2"
            title="Quản lý providers"
          >
            <SettingsIcon size={12} />
          </Link>
          {testingSelected ? (
            <span className="inline-flex items-center gap-1.5 muted">
              <RefreshCw size={10} className="animate-spin" /> đang test{" "}
              {selectedProvider}
            </span>
          ) : llmDown ? (
            <span className="inline-flex items-center gap-1.5 text-[var(--danger)]">
              <span className="dot dot-danger" /> LLM không phản hồi
            </span>
          ) : selectedUnreachable ? (
            <span
              className="inline-flex items-center gap-1.5 text-[var(--warning)]"
              title={`Ping tới ${selectedProvider} timeout/lỗi (${providerStatus?.detail}). Chat thật có timeout rộng hơn — vẫn có thể gửi thử.`}
            >
              <span className="dot dot-danger" /> {selectedProvider} ping chậm
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-[var(--success)]">
              <span className="dot dot-success" /> LLM sẵn sàng
            </span>
          )}
          <button
            type="button"
            onClick={refreshHealth}
            className="muted hover:text-[var(--fg)] p-0.5 rounded"
            title="Kiểm tra lại trạng thái LLM"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {llmDown && (
        <div className="card border border-red-900/60 bg-red-950/30 flex items-start gap-3">
          <AlertTriangle size={24} className="text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1 text-sm">
            <div className="font-medium">
              Không gọi được LLM. Chat tự động không hoạt động.
            </div>
            <div className="muted mt-0.5">
              Vẫn có thể ghi giao dịch bằng form bên dưới. Hoặc đổi provider khác
              ở{" "}
              <Link href="/providers" className="underline">
                trang quản lý
              </Link>
              .
            </div>
          </div>
          <button
            onClick={() => setShowFallback((s) => !s)}
            className="text-sm px-3 py-1 rounded border border-red-900/60 hover:bg-red-900/30"
          >
            {showFallback ? "Ẩn form" : "Hiện form"}
          </button>
        </div>
      )}

      {showFallback && (
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-base font-semibold">Nhập giao dịch thủ công</h2>
            {!llmDown && (
              <button
                onClick={() => setShowFallback(false)}
                className="text-xs muted hover:underline"
              >
                ẩn
              </button>
            )}
          </div>
          <TransactionForm accounts={accounts} categories={categories} />
        </div>
      )}

      <div className="card min-h-[50vh] max-h-[70vh] overflow-auto space-y-3">
        {turns.length === 0 && (
          <div className="muted text-sm flex items-center justify-between">
            <span>
              Thử: <code>trưa nay ăn phở 45k bằng Tiền mặt</code>
            </span>
            {!llmDown && !showFallback && (
              <button
                onClick={() => setShowFallback(true)}
                className="text-xs hover:underline"
                title="Mở form thủ công (dùng khi muốn nhập chính xác)"
              >
                ✋ form thủ công
              </button>
            )}
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i}>
            {t.role === "user" ? (
              <div className="text-right">
                <span className="inline-block bg-[var(--border)] rounded-lg px-3 py-1.5 text-sm">
                  {t.text}
                </span>
              </div>
            ) : (
              <div>
                <div className="text-sm mb-2 muted">🤖 {t.text}</div>
                <div className="flex flex-col gap-2">
                  {t.items.map((it, k) => (
                    <ExtractedTxCard
                      key={k}
                      tx={it}
                      accounts={accounts}
                      categories={categories}
                      onDone={(msg) =>
                        setTurns((x) => [
                          ...x,
                          { role: "assistant", text: msg, items: [] },
                        ])
                      }
                      onMessage={(msg) =>
                        setTurns((x) => [
                          ...x,
                          { role: "assistant", text: msg, items: [] },
                        ])
                      }
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
        {loading && <div className="muted text-sm">...đang xử lý</div>}
      </div>

      <div className="flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={
            llmDown
              ? "LLM đang down — dùng form ở trên để nhập"
              : "VD: sáng cafe 25k, trưa cơm 50k"
          }
          disabled={llmDown}
          className="field flex-1 !py-2.5 disabled:opacity-60"
        />
        <button
          onClick={send}
          disabled={loading || llmDown}
          className="btn btn-grd-primary !py-2.5"
        >
          Gửi
        </button>
      </div>
    </div>
  );
}
