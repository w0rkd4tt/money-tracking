"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useIdleAutoLock } from "@/hooks/useIdleAutoLock";
import { useLockHotkey } from "@/hooks/useLockHotkey";
import { clearSessionMark, isSessionValid } from "@/lib/session-mark";
import { Sidebar } from "./Sidebar";

// Routes that render full-bleed (no sidebar), e.g. pre-unlock pages.
const BARE_PATHS = ["/setup", "/unlock", "/recover"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const isBare =
    BARE_PATHS.includes(pathname) ||
    BARE_PATHS.some((p) => pathname.startsWith(p + "/"));

  // Auto-lock when tab has been away (blurred/hidden) ≥ 5 min. Disabled on
  // bare/unlock pages so the user isn't redirected off the login screen.
  useIdleAutoLock(!isBare);
  // ⌘⇧L / Ctrl⇧L → lock immediately. Same gating.
  useLockHotkey(!isBare);

  // Per-tab session gate. The server cookie `mt_session` is valid for 30
  // days, so a fresh tab (or one restored via Ctrl+Shift+T) that inherited
  // it would bypass the unlock screen without this check. isSessionValid()
  // combines a sessionStorage marker with a Performance Navigation Timing
  // check so tab-restore reliably lands on /unlock.
  const [gateReady, setGateReady] = useState<boolean>(isBare);
  useEffect(() => {
    if (isBare) {
      setGateReady(true);
      return;
    }
    if (isSessionValid()) {
      setGateReady(true);
      return;
    }
    // Stale / restored / fresh tab — force lock. Clear the mark so the next
    // unlock flow sees a clean slate, fire-and-forget logout (preserves user
    // activation for the auto-passkey prompt on /unlock), then navigate.
    clearSessionMark();
    fetch("/api/v1/ui/logout", { method: "POST", cache: "no-store" }).catch(
      () => {
        // offline / 500 — middleware still redirects once cookie is gone
      },
    );
    router.push("/unlock");
    router.refresh();
  }, [isBare, router]);

  if (isBare) {
    return <main className="min-h-screen p-6 max-w-[1400px] mx-auto">{children}</main>;
  }

  // Hold the UI blank while the gate check runs — prevents a flash of the
  // authenticated dashboard on a fresh tab before the redirect fires.
  if (!gateReady) {
    return <div className="min-h-screen bg-[var(--bg)]" />;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 min-w-0 p-6">{children}</main>
    </div>
  );
}
