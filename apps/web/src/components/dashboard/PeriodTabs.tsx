"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

const OPTIONS: { key: "week" | "month" | "year"; label: string }[] = [
  { key: "week", label: "Tuần" },
  { key: "month", label: "Tháng" },
  { key: "year", label: "Năm" },
];

export function PeriodTabs({ current }: { current: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const switchTo = (p: string) => {
    const sp = new URLSearchParams(params.toString());
    sp.set("period", p);
    router.push(`${pathname}?${sp.toString()}`);
  };

  return (
    <div className="inline-flex rounded-lg border border-[var(--border)] p-0.5 text-sm">
      {OPTIONS.map((o) => (
        <button
          key={o.key}
          onClick={() => switchTo(o.key)}
          className={
            "px-4 py-1.5 rounded-md transition " +
            (current === o.key ? "bg-blue-700 text-white" : "hover:bg-[var(--border)]")
          }
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
