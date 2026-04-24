import { api } from "@/lib/api";
import { BackupPanel } from "@/components/settings/BackupPanel";
import { GmailPanel } from "@/components/settings/GmailPanel";
import { HotkeyPanel } from "@/components/settings/HotkeyPanel";
import { PasskeyPanel } from "@/components/settings/PasskeyPanel";
import { SecurityPanel } from "@/components/settings/SecurityPanel";

type Policy = {
  id: number;
  action: string;
  pattern_type: string;
  pattern: string;
  priority: number;
  enabled: boolean;
  note: string | null;
};

type AppSettings = {
  default_account_id: number | null;
  locale: string;
  timezone: string;
  default_currency: string;
  llm_allow_cloud: boolean;
  llm_agent_enabled: boolean;
  llm_gmail_tool_enabled: boolean;
  theme: string;
};

export default async function SettingsPage() {
  const [settings, policies] = await Promise.all([
    api<AppSettings>("/settings"),
    api<Policy[]>("/llm/policies/gmail"),
  ]);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Settings</h1>

      <SecurityPanel />

      <PasskeyPanel />

      <HotkeyPanel />

      <GmailPanel />

      <BackupPanel />

      <section className="card">
        <h2 className="font-semibold mb-2">App</h2>
        <pre className="text-xs muted whitespace-pre-wrap bg-[var(--bg)] border border-[var(--border)] rounded-lg p-3 font-mono">
{JSON.stringify(settings, null, 2)}
        </pre>
      </section>

      <section className="card">
        <h2 className="font-semibold mb-2">LLM Gmail policies</h2>
        <p className="muted text-sm mb-3">
          Quyền LLM đọc Gmail. Mặc định deny-all nếu chưa có allow nào enabled. OTP
          deny luôn active.
        </p>
        {policies.length === 0 ? (
          <p className="muted">Chưa có policy nào.</p>
        ) : (
          <table className="table-clean">
            <thead>
              <tr>
                <th>#</th>
                <th>Action</th>
                <th>Type</th>
                <th>Pattern</th>
                <th>Pri</th>
                <th>On</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>
                    <span
                      className={
                        p.action === "deny" ? "chip chip-danger" : "chip chip-success"
                      }
                    >
                      {p.action}
                    </span>
                  </td>
                  <td>{p.pattern_type}</td>
                  <td className="font-mono text-xs">{p.pattern}</td>
                  <td>{p.priority}</td>
                  <td>{p.enabled ? "✓" : "—"}</td>
                  <td className="muted text-xs">{p.note || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
