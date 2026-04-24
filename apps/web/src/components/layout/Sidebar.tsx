"use client";

import {
  ArrowLeftRight,
  LayoutDashboard,
  Layers,
  List,
  Lock,
  type LucideIcon,
  Mail,
  MessageSquare,
  PieChart,
  Settings as SettingsIcon,
  Tags,
  Target,
  Wallet,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

type Item = {
  href: string;
  label: string;
  icon: LucideIcon;
};

type Group = {
  label: string | null;
  items: Item[];
};

const GROUPS: Group[] = [
  {
    label: null,
    items: [{ href: "/", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Dữ liệu",
    items: [
      { href: "/accounts", label: "Tài khoản", icon: Wallet },
      { href: "/transactions", label: "Giao dịch", icon: List },
      { href: "/transfers", label: "Chuyển khoản", icon: ArrowLeftRight },
      { href: "/categories", label: "Danh mục", icon: Tags },
    ],
  },
  {
    label: "Kế hoạch",
    items: [
      { href: "/buckets", label: "Phân bổ", icon: Layers },
      { href: "/plans", label: "Kế hoạch tháng", icon: Target },
    ],
  },
  {
    label: "Kênh nhập",
    items: [
      { href: "/chat", label: "Chat", icon: MessageSquare },
      { href: "/email-ingest", label: "Email", icon: Mail },
    ],
  },
  {
    label: "Hệ thống",
    items: [
      { href: "/providers", label: "LLM Providers", icon: Zap },
      { href: "/settings", label: "Cài đặt", icon: SettingsIcon },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function logout() {
    setBusy(true);
    try {
      await fetch("/api/v1/ui/logout", { method: "POST", cache: "no-store" });
    } finally {
      setBusy(false);
      router.push("/unlock");
      router.refresh();
    }
  }

  return (
    <aside className="shrink-0 w-60 max-md:w-16 bg-[var(--surface)] border-r border-[var(--border)] min-h-screen sticky top-0 flex flex-col">
      {/* Brand */}
      <div className="px-5 py-5 flex items-center gap-2.5 max-md:justify-center max-md:px-0">
        <span
          className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: "var(--grd-primary)" }}
        >
          <PieChart size={18} className="text-white" strokeWidth={2.5} />
        </span>
        <div className="max-md:hidden leading-tight">
          <div className="font-semibold text-[15px] tracking-tight">Money</div>
          <div className="text-[11px] text-[var(--muted)]">tracking</div>
        </div>
      </div>

      <nav className="flex flex-col gap-0.5 px-3 flex-1 overflow-y-auto">
        {GROUPS.map((group, gi) => (
          <div key={gi} className="mb-3 flex flex-col gap-0.5">
            {group.label && (
              <div className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-[0.08em] text-[var(--muted-soft)] max-md:hidden">
                {group.label}
              </div>
            )}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = isActive(pathname || "/", item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors max-md:justify-center max-md:px-2 " +
                    (active
                      ? "bg-[var(--primary-soft)] text-[var(--primary)]"
                      : "text-[var(--muted)] hover:bg-white/[0.04] hover:text-[var(--fg)]")
                  }
                  title={item.label}
                >
                  <Icon size={17} className="shrink-0" strokeWidth={active ? 2.25 : 2} />
                  <span className="max-md:hidden">{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="px-3 pb-4 pt-3 border-t border-[var(--border)]">
        <button
          onClick={logout}
          disabled={busy}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium w-full text-[var(--muted)] hover:bg-red-500/10 hover:text-[var(--danger)] disabled:opacity-50 transition-colors max-md:justify-center max-md:px-2"
          title="Khoá giao diện"
        >
          <Lock size={16} className="shrink-0" />
          <span className="max-md:hidden">Khoá giao diện</span>
        </button>
      </div>
    </aside>
  );
}
