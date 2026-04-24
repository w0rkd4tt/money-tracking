import Link from "next/link";
import { redirect } from "next/navigation";
import { RecoverForm } from "@/components/ui-unlock/RecoverForm";
import { api } from "@/lib/api";

type Status = { configured: boolean; unlocked: boolean };

export default async function RecoverPage() {
  let status: Status | null = null;
  try {
    status = await api<Status>("/ui/status");
  } catch {
    // API unreachable — user will see error on submit
  }
  if (status && !status.configured) redirect("/setup");

  return (
    <div className="max-w-md mx-auto flex flex-col gap-4 py-8">
      <div>
        <h1 className="text-2xl font-bold">🆘 Khôi phục mã PIN</h1>
        <p className="muted text-sm mt-1">
          Nhập khoá khôi phục (dạng <code>XXXX-XXXX-...</code>) bạn đã lưu lúc
          thiết lập để đặt mã PIN mới.
        </p>
      </div>
      <RecoverForm />
      <div className="text-sm text-center">
        <Link href="/unlock" className="muted hover:underline">
          ← Quay lại mở khoá
        </Link>
      </div>
    </div>
  );
}
