import { redirect } from "next/navigation";
import { SetupForm } from "@/components/ui-unlock/SetupForm";
import { api } from "@/lib/api";

type Status = { configured: boolean; unlocked: boolean };

export default async function SetupPage() {
  let status: Status | null = null;
  try {
    status = await api<Status>("/ui/status");
  } catch {
    // API unreachable — user will see error on submit
  }
  if (status?.configured) redirect(status.unlocked ? "/" : "/unlock");

  return (
    <div className="max-w-md mx-auto flex flex-col gap-4 py-8">
      <div>
        <h1 className="text-2xl font-bold">🔐 Thiết lập lần đầu</h1>
        <p className="muted text-sm mt-1">
          Tạo mã PIN 6 chữ số để khoá giao diện web. Sau đó bạn sẽ nhận một{" "}
          <strong>khoá khôi phục (recovery key)</strong> — lưu ngay vì chỉ hiển
          thị <em>một lần</em>.
        </p>
      </div>
      <SetupForm />
    </div>
  );
}
