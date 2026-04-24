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
  PanelLeftClose,
  PanelLeftOpen,
  PieChart,
  Settings as SettingsIcon,
  Tags,
  Target,
  Wallet,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  HOTKEY_CHANGED_EVENT,
  defaultLockHotkey,
  formatHotkey,
  loadLockHotkey,
} from "@/lib/hotkey";

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

const COLLAPSE_KEY = "mt_sidebar_collapsed";

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  // Start collapsed=false so the SSR pass matches the first client render.
  // Hydrate real value in useEffect — a brief flash of expanded state on
  // cold load is acceptable; avoids SSR/client hydration mismatch.
  const [collapsed, setCollapsed] = useState(false);
  const [shortcutHint, setShortcutHint] = useState<string>(() =>
    formatHotkey(defaultLockHotkey()),
  );

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      // storage disabled — leave expanded
    }
    setShortcutHint(formatHotkey(loadLockHotkey()));
    function onHotkeyChanged() {
      setShortcutHint(formatHotkey(loadLockHotkey()));
    }
    window.addEventListener(HOTKEY_CHANGED_EVENT, onHotkeyChanged);
    return () =>
      window.removeEventListener(HOTKEY_CHANGED_EVENT, onHotkeyChanged);
  }, []);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        // ignore
      }
      return next;
    });
  }

  function logout() {
    setBusy(true);
    fetch("/api/v1/ui/logout", { method: "POST", cache: "no-store" })
      .catch(() => {
        // Offline / 500 — /unlock re-checks status anyway.
      })
      .finally(() => setBusy(false));
    router.push("/unlock");
    router.refresh();
  }

  // Mobile screens always render the compact layout via `max-md:*` utilities.
  // When `collapsed` is true on desktop, we hoist those same compact classes
  // so the sidebar looks exactly like mobile at all widths. Extracted into
  // helpers so we don't duplicate the conditional everywhere.
  const textHidden = collapsed ? "hidden" : "max-md:hidden";
  const rowCompact = collapsed
    ? "justify-center px-2"
    : "max-md:justify-center max-md:px-2";
  const brandCompact = collapsed
    ? "justify-center px-0"
    : "max-md:justify-center max-md:px-0";
  const widthClass = collapsed ? "w-16" : "w-60 max-md:w-16";

  return (
    <aside
      className={
        "shrink-0 sticky top-0 h-screen flex flex-col bg-[var(--surface)] border-r border-[var(--border)] transition-[width] duration-200 " +
        widthClass
      }
    >
      {/* Brand */}
      <div className={"px-5 py-5 flex items-center gap-2.5 " + brandCompact}>
        <span
          className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: "var(--grd-primary)" }}
        >
          <PieChart size={18} className="text-white" strokeWidth={2.5} />
        </span>
        <div className={"leading-tight " + textHidden}>
          <div className="font-semibold text-[15px] tracking-tight">Money</div>
          <div className="text-[11px] text-[var(--muted)]">tracking</div>
        </div>
      </div>

      <nav className="flex flex-col gap-0.5 px-3 flex-1 overflow-y-auto">
        {GROUPS.map((group, gi) => (
          <div key={gi} className="mb-3 flex flex-col gap-0.5">
            {group.label && (
              <div
                className={
                  "px-3 pt-3 pb-1 text-[10px] uppercase tracking-[0.08em] text-[var(--muted-soft)] " +
                  textHidden
                }
              >
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
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors " +
                    rowCompact +
                    " " +
                    (active
                      ? "bg-[var(--primary-soft)] text-[var(--primary)]"
                      : "text-[var(--muted)] hover:bg-white/[0.04] hover:text-[var(--fg)]")
                  }
                  title={item.label}
                >
                  <Icon size={17} className="shrink-0" strokeWidth={active ? 2.25 : 2} />
                  <span className={textHidden}>{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="px-3 pb-4 pt-3 border-t border-[var(--border)] flex flex-col gap-1">
        <button
          onClick={toggleCollapsed}
          className={
            "flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium w-full text-[var(--muted)] hover:bg-white/[0.04] hover:text-[var(--fg)] transition-colors max-md:hidden " +
            (collapsed ? "justify-center px-2" : "")
          }
          title={collapsed ? "Mở rộng menu" : "Thu gọn menu"}
          aria-label={collapsed ? "Mở rộng menu" : "Thu gọn menu"}
        >
          {collapsed ? (
            <PanelLeftOpen size={16} className="shrink-0" />
          ) : (
            <PanelLeftClose size={16} className="shrink-0" />
          )}
          <span className={textHidden + " flex-1 text-left"}>Thu gọn</span>
        </button>

        <button
          onClick={logout}
          disabled={busy}
          className={
            "flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium w-full text-[var(--muted)] hover:bg-red-500/10 hover:text-[var(--danger)] disabled:opacity-50 transition-colors " +
            rowCompact
          }
          title={`Khoá giao diện (${shortcutHint})`}
        >
          <Lock size={16} className="shrink-0" />
          <span className={textHidden + " flex-1 text-left"}>Khoá giao diện</span>
          <kbd
            className={
              textHidden +
              " text-[10px] font-mono text-[var(--muted-soft)] border border-[var(--border)] rounded px-1.5 py-0.5"
            }
          >
            {shortcutHint}
          </kbd>
        </button>
      </div>
    </aside>
  );
}
