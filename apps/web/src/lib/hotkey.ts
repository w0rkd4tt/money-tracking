/**
 * Lock-hotkey storage + matching.
 *
 * We persist the user's chosen combo in localStorage (not the DB) because:
 * - It's single-user and per-browser UX. A user on two browsers might prefer
 *   different combos; persisting it server-side would force synchronisation
 *   logic that nobody wants.
 * - No latency / round-trip at page load.
 *
 * Contract: at least one of ctrl/meta/alt must be set — shift alone would
 * collide with plain typing (e.g. shift+A producing 'A'). We enforce this in
 * `isValidHotkey` before save.
 */

export type LockHotkey = {
  ctrl: boolean;
  meta: boolean;
  shift: boolean;
  alt: boolean;
  // event.key, normalised to uppercase for letters. Special keys keep their
  // spec name (e.g. "Enter", "Escape", "F1") — not uppercased.
  key: string;
};

const STORAGE_KEY = "mt_lock_hotkey";
export const HOTKEY_CHANGED_EVENT = "mt_lock_hotkey:changed";

const isMac = (): boolean =>
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export function defaultLockHotkey(): LockHotkey {
  return isMac()
    ? { meta: true, shift: true, ctrl: false, alt: false, key: "L" }
    : { ctrl: true, shift: true, meta: false, alt: false, key: "L" };
}

export function loadLockHotkey(): LockHotkey {
  if (typeof window === "undefined") return defaultLockHotkey();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultLockHotkey();
    const parsed = JSON.parse(raw) as LockHotkey;
    if (!isValidHotkey(parsed)) return defaultLockHotkey();
    return parsed;
  } catch {
    return defaultLockHotkey();
  }
}

export function saveLockHotkey(hk: LockHotkey): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(hk));
  window.dispatchEvent(new CustomEvent(HOTKEY_CHANGED_EVENT));
}

export function resetLockHotkey(): void {
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new CustomEvent(HOTKEY_CHANGED_EVENT));
}

/**
 * At least one real modifier so the binding doesn't fire while typing. Key
 * must be non-empty and not a bare modifier (Control/Meta/Shift/Alt alone).
 */
export function isValidHotkey(hk: LockHotkey): boolean {
  if (!hk || typeof hk !== "object") return false;
  if (!hk.ctrl && !hk.meta && !hk.alt) return false;
  if (!hk.key) return false;
  const bareModifier = ["Control", "Meta", "Shift", "Alt", "OS"].includes(hk.key);
  if (bareModifier) return false;
  return true;
}

/**
 * Turn a keydown event into a hotkey record. Returns null for bare-modifier
 * events so the recorder UI can ignore them until the user presses a real key.
 */
export function eventToHotkey(e: KeyboardEvent): LockHotkey | null {
  const rawKey = e.key;
  if (["Control", "Meta", "Shift", "Alt", "OS", "Dead"].includes(rawKey)) {
    return null;
  }
  const key = rawKey.length === 1 ? rawKey.toUpperCase() : rawKey;
  return {
    ctrl: e.ctrlKey,
    meta: e.metaKey,
    shift: e.shiftKey,
    alt: e.altKey,
    key,
  };
}

export function hotkeyMatches(e: KeyboardEvent, hk: LockHotkey): boolean {
  if (e.ctrlKey !== hk.ctrl) return false;
  if (e.metaKey !== hk.meta) return false;
  if (e.shiftKey !== hk.shift) return false;
  if (e.altKey !== hk.alt) return false;
  const pressed = e.key.length === 1 ? e.key.toUpperCase() : e.key;
  return pressed === hk.key;
}

/** Render as e.g. "⌘⇧L" on Mac, "Ctrl+Shift+L" elsewhere. */
export function formatHotkey(hk: LockHotkey): string {
  const mac = isMac();
  const parts: string[] = [];
  if (mac) {
    if (hk.ctrl) parts.push("⌃");
    if (hk.alt) parts.push("⌥");
    if (hk.shift) parts.push("⇧");
    if (hk.meta) parts.push("⌘");
    parts.push(hk.key);
    return parts.join("");
  }
  if (hk.ctrl) parts.push("Ctrl");
  if (hk.meta) parts.push("Win");
  if (hk.alt) parts.push("Alt");
  if (hk.shift) parts.push("Shift");
  parts.push(hk.key);
  return parts.join("+");
}
