import Link from "next/link";
import { redirect } from "next/navigation";
import { PasskeyUnlockButton } from "@/components/ui-unlock/PasskeyUnlockButton";
import { UnlockForm } from "@/components/ui-unlock/UnlockForm";
import { api } from "@/lib/api";

type Status = {
  configured: boolean;
  unlocked: boolean;
  passkey_count: number;
};

export default async function UnlockPage() {
  let status: Status | null = null;
  try {
    status = await api<Status>("/ui/status");
  } catch {
    // API unreachable — render form, user will see error on submit
  }
  if (status && !status.configured) redirect("/setup");
  if (status && status.unlocked) redirect("/");

  const hasPasskey = (status?.passkey_count ?? 0) > 0;

  return (
    <div className="max-w-md mx-auto flex flex-col gap-4 py-8">
      <div>
        <h1 className="text-2xl font-bold">🔒 Mở khoá</h1>
        <p className="muted text-sm mt-1">
          {hasPasskey
            ? "Dùng passkey (Touch ID / Face ID) hoặc nhập mã PIN 6 chữ số."
            : "Nhập mã PIN 6 chữ số để truy cập giao diện."}
        </p>
      </div>
      {hasPasskey && (
        <>
          <PasskeyUnlockButton autoTrigger />
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-[var(--border)]" />
            <span className="muted text-xs uppercase tracking-wide">hoặc PIN</span>
            <div className="flex-1 h-px bg-[var(--border)]" />
          </div>
        </>
      )}
      <UnlockForm />
      <div className="text-sm text-center">
        <Link href="/recover" className="muted hover:underline">
          Quên PIN? Dùng khoá khôi phục →
        </Link>
      </div>
    </div>
  );
}
