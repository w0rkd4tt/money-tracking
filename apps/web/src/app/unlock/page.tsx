import Link from "next/link";
import { redirect } from "next/navigation";
import { UnlockForm } from "@/components/ui-unlock/UnlockForm";
import { api } from "@/lib/api";

type Status = { configured: boolean; unlocked: boolean };

export default async function UnlockPage() {
  let status: Status | null = null;
  try {
    status = await api<Status>("/ui/status");
  } catch {
    // API unreachable — render form, user will see error on submit
  }
  if (status && !status.configured) redirect("/setup");
  if (status && status.unlocked) redirect("/");

  return (
    <div className="max-w-md mx-auto flex flex-col gap-4 py-8">
      <div>
        <h1 className="text-2xl font-bold">🔒 Mở khoá</h1>
        <p className="muted text-sm mt-1">Nhập mật khẩu để truy cập giao diện.</p>
      </div>
      <UnlockForm />
      <div className="text-sm text-center">
        <Link href="/recover" className="muted hover:underline">
          Quên mật khẩu? Dùng khoá khôi phục →
        </Link>
      </div>
    </div>
  );
}
