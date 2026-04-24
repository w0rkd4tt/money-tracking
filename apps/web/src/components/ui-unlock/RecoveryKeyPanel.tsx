"use client";

import { AlertTriangle, ArrowRight, Check, Copy, Download } from "lucide-react";
import { useState } from "react";

export function RecoveryKeyPanel({
  recoveryKey,
  label,
  onContinue,
}: {
  recoveryKey: string;
  label: string;
  onContinue: () => void;
}) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [copiedAt, setCopiedAt] = useState<number | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(recoveryKey);
      setCopiedAt(Date.now());
      setTimeout(() => setCopiedAt(null), 2000);
    } catch {
      // ignore
    }
  }

  function download() {
    const blob = new Blob(
      [
        `Money Tracking — Recovery Key\n`,
        `Generated: ${new Date().toISOString()}\n\n`,
        `${recoveryKey}\n\n`,
        `Use this to reset your passphrase if you forget it.\n`,
        `Keep it offline and private.\n`,
      ],
      { type: "text/plain" }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `money-recovery-key-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="card flex flex-col gap-3 border border-amber-900/60 bg-amber-950/20">
      <div>
        <h2 className="font-semibold flex items-center gap-2 text-amber-300">
          <AlertTriangle size={18} /> {label}
        </h2>
        <p className="muted text-sm mt-1">
          Khoá này chỉ hiện <strong>một lần</strong>. Dùng để lấy lại truy cập
          nếu quên mật khẩu. Lưu offline (password manager / giấy in), KHÔNG
          chụp màn hình cloud.
        </p>
      </div>

      <div className="bg-[var(--card)] border border-[var(--border)] rounded p-4 font-mono text-lg text-center break-all select-all">
        {recoveryKey}
      </div>

      <div className="flex gap-2 flex-wrap">
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 border border-[var(--border)] text-sm px-3 py-1.5 rounded hover:bg-[var(--border)]/40"
        >
          {copiedAt ? (
            <>
              <Check size={14} /> Đã copy
            </>
          ) : (
            <>
              <Copy size={14} /> Copy
            </>
          )}
        </button>
        <button
          type="button"
          onClick={download}
          className="inline-flex items-center gap-1.5 border border-[var(--border)] text-sm px-3 py-1.5 rounded hover:bg-[var(--border)]/40"
        >
          <Download size={14} /> Download .txt
        </button>
      </div>

      <label className="flex items-start gap-2 text-sm mt-2">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={acknowledged}
          onChange={(e) => setAcknowledged(e.target.checked)}
        />
        <span>
          Tôi đã lưu khoá khôi phục ở nơi an toàn. Tôi hiểu nếu mất khoá này
          và quên mật khẩu, không có cách nào lấy lại giao diện (dữ liệu DB
          plaintext vẫn còn — restore từ backup).
        </span>
      </label>

      <button
        type="button"
        disabled={!acknowledged}
        onClick={onContinue}
        className="inline-flex items-center gap-1.5 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm px-4 py-2 rounded self-start"
      >
        Tiếp tục <ArrowRight size={14} />
      </button>
    </div>
  );
}
