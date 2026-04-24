"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  HOTKEY_CHANGED_EVENT,
  hotkeyMatches,
  loadLockHotkey,
  type LockHotkey,
} from "@/lib/hotkey";

/**
 * Global "lock now" keyboard shortcut. Binding is user-configurable via the
 * HotkeyPanel in /settings; reads from localStorage and re-reads when the
 * panel dispatches HOTKEY_CHANGED_EVENT (so save-and-go-back Just Works,
 * no refresh needed).
 *
 * Disabled on the pre-unlock pages (setup/unlock/recover) so the shortcut
 * doesn't fire while the user is typing their PIN.
 */
export function useLockHotkey(enabled: boolean) {
  const router = useRouter();
  const hkRef = useRef<LockHotkey>(loadLockHotkey());

  useEffect(() => {
    if (!enabled) return;

    function onKey(e: KeyboardEvent) {
      if (hotkeyMatches(e, hkRef.current)) {
        e.preventDefault();
        // Fire-and-forget the logout: we navigate to /unlock immediately so
        // the user's transient activation from this keydown still propagates
        // to the auto-triggered passkey ceremony on the next page. Awaiting
        // the fetch here would consume the activation and Safari would then
        // reject navigator.credentials.get() with NotAllowedError.
        fetch("/api/v1/ui/logout", { method: "POST", cache: "no-store" }).catch(
          () => {
            // Offline / 500 — /unlock re-checks status anyway.
          },
        );
        router.push("/unlock");
        router.refresh();
      }
    }

    function onHotkeyChanged() {
      hkRef.current = loadLockHotkey();
    }

    window.addEventListener("keydown", onKey);
    window.addEventListener(HOTKEY_CHANGED_EVENT, onHotkeyChanged);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(HOTKEY_CHANGED_EVENT, onHotkeyChanged);
    };
  }, [enabled, router]);
}
