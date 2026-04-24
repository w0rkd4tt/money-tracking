/**
 * Per-tab "still logged in" gate.
 *
 * The server-side `mt_session` cookie is valid for 30 days. That's the long
 * tail session. But the user wants: **close the tab, reopen → locked**, even
 * when the cookie is still fresh. Straightforward sessionStorage isn't enough
 * because Ctrl+Shift+T (undo-close-tab) RESTORES sessionStorage verbatim in
 * Chrome/Firefox/Safari.
 *
 * Two layers give us per-tab-lifetime semantics:
 *
 * 1. sessionStorage `mt_active_tab` — set on successful auth. Empty in a
 *    fresh tab (typed URL, bookmark). Restored by Ctrl+Shift+T.
 *
 * 2. Module-level `inContextAuthenticated` — set on successful auth. Lost
 *    whenever the JS runtime re-initialises (reload OR Ctrl+Shift+T give us
 *    a fresh runtime). Reload is legitimate so we restore this flag when we
 *    see `navigation.type === 'reload'`. Ctrl+Shift+T yields
 *    `'back_forward'` → we refuse to restore the flag, forcing unlock.
 *
 * Truth table:
 *
 *   sessionStorage | in-context | nav.type       | verdict
 *   ---------------|-----------|----------------|----------
 *   empty          | —          | anything       | lock (fresh tab)
 *   set            | true       | —              | ok (in-app nav after unlock)
 *   set            | false      | reload         | ok (F5 — re-adopt flag)
 *   set            | false      | back_forward   | lock (tab restore)
 *   set            | false      | navigate       | ok (edge: fresh JS ctx on a
 *                                                 set storage — treat as reload)
 */

const KEY = "mt_active_tab";

/**
 * True once markSession() has fired in this exact JS runtime. Survives
 * SPA navigations (same runtime) but NOT reload or tab-restore (both spin
 * up a new runtime).
 */
let inContextAuthenticated = false;

export function markSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(KEY, "1");
  } catch {
    // Private mode — accept the risk; idle auto-lock still applies.
  }
  inContextAuthenticated = true;
}

export function clearSessionMark(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
  inContextAuthenticated = false;
}

function readNavType(): string | null {
  if (typeof performance === "undefined") return null;
  try {
    const entries = performance.getEntriesByType(
      "navigation",
    ) as PerformanceNavigationTiming[];
    return entries[0]?.type ?? null;
  } catch {
    return null;
  }
}

/**
 * Gate used by AppShell. Returns true iff the tab is currently authenticated
 * from this browser-tab lifetime — false for fresh tabs or tabs restored via
 * Ctrl+Shift+T / session restore.
 */
export function isSessionValid(): boolean {
  if (typeof window === "undefined") return true;

  let marked: boolean;
  try {
    marked = window.sessionStorage.getItem(KEY) === "1";
  } catch {
    return true; // storage disabled → fail open so UI isn't bricked
  }
  if (!marked) return false;

  if (inContextAuthenticated) return true;

  // sessionStorage says we were authenticated but this JS context is fresh:
  // it's either a reload (legit — re-adopt the flag) or a Ctrl+Shift+T
  // restore (treat as fresh tab → lock).
  const navType = readNavType();
  if (navType === "back_forward") return false;

  // Reload or navigate with an existing marker → adopt as this context's
  // authenticated state so subsequent checks skip the nav-type branch.
  inContextAuthenticated = true;
  return true;
}
