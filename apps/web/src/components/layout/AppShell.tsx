"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";

// Routes that render full-bleed (no sidebar), e.g. pre-unlock pages.
const BARE_PATHS = ["/setup", "/unlock", "/recover"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const isBare =
    BARE_PATHS.includes(pathname) ||
    BARE_PATHS.some((p) => pathname.startsWith(p + "/"));

  if (isBare) {
    return <main className="min-h-screen p-6 max-w-[1400px] mx-auto">{children}</main>;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 min-w-0 p-6">{children}</main>
    </div>
  );
}
