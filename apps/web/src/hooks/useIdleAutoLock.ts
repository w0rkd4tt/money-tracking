"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const TIMEOUT_MS = 5 * 60 * 1000;

/**
 * Locks the UI (deletes `mt_session` cookie → redirects to /unlock) when the
 * user has been away from the tab for longer than TIMEOUT_MS. "Away" means
 * either the document is hidden OR the window lost focus — so switching to
 * another app, minimising the browser, or just clicking into another tab all
 * start the clock. Coming back before the timeout clears it; coming back
 * after it triggers the lock immediately (covers background-throttled
 * setTimeouts that never fire while the tab is inactive).
 */
export function useIdleAutoLock(enabled: boolean) {
  const router = useRouter();

  useEffect(() => {
    if (!enabled) return;

    let locking = false;
    let awaySince: number | null = null;
    let timer: number | null = null;

    async function lock() {
      if (locking) return;
      locking = true;
      try {
        await fetch("/api/v1/ui/logout", { method: "POST", cache: "no-store" });
      } catch {
        // Network failure — still redirect. The cookie may or may not be
        // gone, but /unlock will handle both cases cleanly.
      }
      router.push("/unlock");
      router.refresh();
    }

    function isAway(): boolean {
      return document.visibilityState === "hidden" || !document.hasFocus();
    }

    function clearTimer() {
      if (timer != null) {
        window.clearTimeout(timer);
        timer = null;
      }
    }

    function sync() {
      if (isAway()) {
        if (awaySince == null) {
          awaySince = Date.now();
          clearTimer();
          // Schedule a best-effort fire. Background tabs may throttle this —
          // the `else` branch below catches that on return.
          timer = window.setTimeout(() => {
            if (isAway()) lock();
          }, TIMEOUT_MS);
        }
      } else {
        if (awaySince != null && Date.now() - awaySince >= TIMEOUT_MS) {
          lock();
        }
        awaySince = null;
        clearTimer();
      }
    }

    window.addEventListener("blur", sync);
    window.addEventListener("focus", sync);
    document.addEventListener("visibilitychange", sync);

    // Start immediately in case the tab was already hidden on mount.
    sync();

    return () => {
      window.removeEventListener("blur", sync);
      window.removeEventListener("focus", sync);
      document.removeEventListener("visibilitychange", sync);
      clearTimer();
    };
  }, [enabled, router]);
}
