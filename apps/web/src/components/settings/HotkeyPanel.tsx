"use client";

import { Keyboard, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  HOTKEY_CHANGED_EVENT,
  defaultLockHotkey,
  eventToHotkey,
  formatHotkey,
  isValidHotkey,
  loadLockHotkey,
  resetLockHotkey,
  saveLockHotkey,
  type LockHotkey,
} from "@/lib/hotkey";

export function HotkeyPanel() {
  const [current, setCurrent] = useState<LockHotkey>(() => defaultLockHotkey());
  const [recording, setRecording] = useState(false);
  const [draft, setDraft] = useState<LockHotkey | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const captureRef = useRef<HTMLDivElement | null>(null);

  // Defer the localStorage read to after hydration so server-rendered HTML
  // (which can't know localStorage) matches the first client render.
  useEffect(() => {
    setCurrent(loadLockHotkey());
    function onChanged() {
      setCurrent(loadLockHotkey());
    }
    window.addEventListener(HOTKEY_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(HOTKEY_CHANGED_EVENT, onChanged);
  }, []);

  // While in recording mode, any keydown is captured. We use a ref'd focused
  // div to scope the listener naturally, but `keydown` bubbles to window so
  // we gate on `recording` state instead of target.
  useEffect(() => {
    if (!recording) return;
    function onKey(e: KeyboardEvent) {
      e.preventDefault();
      e.stopPropagation();
      const hk = eventToHotkey(e);
      if (!hk) return; // bare modifier, wait for the real key
      setDraft(hk);
      if (isValidHotkey(hk)) {
        setErr(null);
      } else {
        setErr("Cần ít nhất 1 modifier: Ctrl / ⌘ / Alt");
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [recording]);

  function startRecording() {
    setErr(null);
    setDraft(null);
    setRecording(true);
    // Focus the capture area so screen readers announce recording state.
    queueMicrotask(() => captureRef.current?.focus());
  }

  function saveDraft() {
    if (!draft || !isValidHotkey(draft)) return;
    saveLockHotkey(draft);
    setRecording(false);
    setDraft(null);
  }

  function cancelRecording() {
    setRecording(false);
    setDraft(null);
    setErr(null);
  }

  function reset() {
    resetLockHotkey();
    setDraft(null);
    setRecording(false);
    setErr(null);
  }

  const active = draft ?? current;
  const showing = recording ? draft : current;

  return (
    <section className="card">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold flex items-center gap-2">
          <Keyboard size={18} /> Hotkey khoá giao diện
        </h2>
        <button
          onClick={reset}
          className="text-xs muted hover:text-[var(--fg)] inline-flex items-center gap-1"
          title="Reset về mặc định"
        >
          <RotateCcw size={13} /> Reset
        </button>
      </div>
      <p className="muted text-xs mt-2">
        Phím tắt để khoá giao diện ngay lập tức. Phải có ít nhất 1 modifier
        (Ctrl / ⌘ / Alt) để tránh xung đột khi gõ chữ. Mặc định:{" "}
        <kbd className="font-mono">{formatHotkey(defaultLockHotkey())}</kbd>.
      </p>

      <div className="mt-3 flex items-center gap-3 flex-wrap">
        <div
          ref={captureRef}
          tabIndex={recording ? 0 : -1}
          className={
            "inline-flex items-center gap-2 px-3 py-2 rounded-lg border font-mono text-sm " +
            (recording
              ? "border-[var(--primary)] bg-[var(--primary-soft)] text-[var(--primary)] outline-none"
              : "border-[var(--border)]")
          }
          aria-live="polite"
        >
          <Keyboard size={14} />
          {showing ? formatHotkey(showing) : recording ? "Đang chờ phím…" : "—"}
        </div>

        {!recording ? (
          <button onClick={startRecording} className="btn btn-grd-primary text-sm">
            Ghi lại
          </button>
        ) : (
          <>
            <button
              onClick={saveDraft}
              disabled={!draft || !isValidHotkey(draft)}
              className="btn btn-grd-primary text-sm disabled:opacity-50"
            >
              Lưu
            </button>
            <button
              onClick={cancelRecording}
              className="btn btn-ghost text-sm"
            >
              Huỷ
            </button>
          </>
        )}
      </div>

      {err && <div className="neg text-xs mt-2">{err}</div>}
      {recording && !err && (
        <div className="muted text-xs mt-2">
          Nhấn tổ hợp phím bạn muốn. Nhấn Huỷ nếu đổi ý.
        </div>
      )}
      {!recording && (
        <div className="muted text-xs mt-2">
          Đang dùng: <kbd className="font-mono">{formatHotkey(active)}</kbd>
        </div>
      )}
    </section>
  );
}
