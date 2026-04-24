import { ProvidersManager } from "@/components/providers/ProvidersManager";
import { api } from "@/lib/api";

type Provider = {
  id: string;
  source: "builtin" | "custom";
  name: string;
  endpoint: string;
  model: string;
  timeout_sec: number;
  enabled: boolean;
  is_default: boolean;
  has_api_key: boolean;
};

export default async function ProvidersPage() {
  let providers: Provider[] = [];
  let fetchErr: string | null = null;
  try {
    providers = await api<Provider[]>("/llm/providers");
  } catch (e) {
    fetchErr = (e as Error).message;
  }

  if (fetchErr) {
    return (
      <div className="card">
        <h1 className="text-xl font-bold mb-2">LLM Providers</h1>
        <p className="neg">Không tải được danh sách providers: {fetchErr}</p>
      </div>
    );
  }

  return <ProvidersManager initialProviders={providers} />;
}
