"use client";

import { Archive, ArchiveRestore, Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";

type Bucket = {
  id: number;
  name: string;
  icon: string | null;
  color: string | null;
  sort_order: number;
  archived: boolean;
  note: string | null;
  category_ids: number[];
};

type Category = {
  id: number;
  name: string;
  path: string;
};

const COLORS = [
  "#16a34a",
  "#0ea5e9",
  "#a855f7",
  "#ec4899",
  "#f59e0b",
  "#ef4444",
  "#14b8a6",
  "#6b7280",
];

const PRESET_ICONS = ["🏠", "🎉", "💰", "📈", "🛒", "🚗", "🎓", "💳", "💵", "🎁"];

async function fetchJSON<T>(
  path: string,
  init?: RequestInit & { json?: unknown }
): Promise<T> {
  const opts: RequestInit = { ...init };
  if (init?.json !== undefined) {
    opts.method = opts.method || "POST";
    opts.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    opts.body = JSON.stringify(init.json);
  }
  const r = await fetch(path, { cache: "no-store", ...opts });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  if (r.status === 204) return undefined as T;
  return r.json();
}

type FormState = {
  name: string;
  icon: string;
  color: string;
  sort_order: string;
  note: string;
  category_ids: number[];
};

const emptyForm: FormState = {
  name: "",
  icon: "🪣",
  color: "#16a34a",
  sort_order: "0",
  note: "",
  category_ids: [],
};

function BucketForm({
  initial,
  allCategories,
  usedByOther,
  onSubmit,
  onCancel,
  submitLabel,
}: {
  initial: FormState;
  allCategories: Category[];
  usedByOther: Map<number, string>; // category_id → bucket name (other than current)
  onSubmit: (v: FormState) => Promise<void>;
  onCancel: () => void;
  submitLabel: string;
}) {
  const [v, setV] = useState<FormState>(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const toggleCat = (id: number) => {
    setV((s) =>
      s.category_ids.includes(id)
        ? { ...s, category_ids: s.category_ids.filter((x) => x !== id) }
        : { ...s, category_ids: [...s.category_ids, id] }
    );
  };

  async function submit() {
    setErr(null);
    if (!v.name.trim()) {
      setErr("Tên nhóm bắt buộc");
      return;
    }
    setBusy(true);
    try {
      await onSubmit(v);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex gap-3 items-end flex-wrap">
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Tên nhóm</span>
          <input
            className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5"
            value={v.name}
            onChange={(e) => setV({ ...v, name: e.target.value })}
            placeholder="Thiết yếu, Mong muốn, Tiết kiệm…"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Icon</span>
          <div className="flex gap-1 flex-wrap max-w-[260px]">
            {PRESET_ICONS.map((ic) => (
              <button
                key={ic}
                type="button"
                onClick={() => setV({ ...v, icon: ic })}
                className={`w-8 h-8 rounded border text-lg ${
                  v.icon === ic
                    ? "border-white"
                    : "border-[var(--border)] hover:border-white/40"
                }`}
              >
                {ic}
              </button>
            ))}
          </div>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Màu</span>
          <div className="flex gap-1 flex-wrap">
            {COLORS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setV({ ...v, color: c })}
                className={`w-6 h-6 rounded-full border-2 ${
                  v.color === c ? "border-white" : "border-transparent"
                }`}
                style={{ backgroundColor: c }}
              />
            ))}
          </div>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="muted">Thứ tự</span>
          <input
            type="number"
            className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5 w-20"
            value={v.sort_order}
            onChange={(e) => setV({ ...v, sort_order: e.target.value })}
          />
        </label>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        <span className="muted">Ghi chú (tuỳ chọn)</span>
        <input
          className="bg-[var(--card)] border border-[var(--border)] rounded px-2 py-1.5"
          value={v.note}
          onChange={(e) => setV({ ...v, note: e.target.value })}
        />
      </label>

      <div className="flex flex-col gap-2">
        <span className="muted text-sm">
          Danh mục chi tiêu thuộc nhóm này ({v.category_ids.length} đã chọn)
        </span>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-1 max-h-64 overflow-auto border border-[var(--border)] rounded p-2">
          {allCategories.map((c) => {
            const owned = usedByOther.get(c.id);
            const checked = v.category_ids.includes(c.id);
            return (
              <label
                key={c.id}
                className={`flex items-center gap-2 text-sm px-1 py-0.5 rounded hover:bg-[var(--border)]/30 cursor-pointer ${
                  owned && !checked ? "opacity-60" : ""
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleCat(c.id)}
                />
                <span>{c.path || c.name}</span>
                {owned && !checked && (
                  <span className="text-xs muted">({owned})</span>
                )}
              </label>
            );
          })}
          {allCategories.length === 0 && (
            <span className="muted text-sm col-span-full">
              Chưa có category kind=expense. Tạo trong trang Categories trước.
            </span>
          )}
        </div>
        <span className="text-xs muted">
          1 danh mục chỉ thuộc 1 nhóm. Chọn ở đây sẽ chuyển từ nhóm cũ (nếu có) sang nhóm này.
        </span>
      </div>

      {err && <div className="neg text-sm">{err}</div>}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={busy}
          className="bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white text-sm px-4 py-1.5 rounded"
        >
          {busy ? "…" : submitLabel}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="border border-[var(--border)] text-sm px-4 py-1.5 rounded hover:bg-[var(--border)]/40"
        >
          Huỷ
        </button>
      </div>
    </div>
  );
}

export function BucketsManager({
  initialBuckets,
  categories,
}: {
  initialBuckets: Bucket[];
  categories: Category[];
}) {
  const [buckets, setBuckets] = useState<Bucket[]>(initialBuckets);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const refresh = useCallback(async () => {
    const data = await fetchJSON<Bucket[]>("/api/v1/buckets?include_archived=true");
    setBuckets(data);
  }, []);

  const catById = new Map(categories.map((c) => [c.id, c]));
  const visible = buckets.filter((b) => showArchived || !b.archived);

  function usedByOther(excludeBucketId: number | null): Map<number, string> {
    const m = new Map<number, string>();
    for (const b of buckets) {
      if (b.id === excludeBucketId) continue;
      for (const cid of b.category_ids) m.set(cid, b.name);
    }
    return m;
  }

  async function onCreate(v: FormState) {
    await fetchJSON("/api/v1/buckets", {
      json: {
        name: v.name.trim(),
        icon: v.icon || null,
        color: v.color || null,
        sort_order: Number(v.sort_order) || 0,
        note: v.note.trim() || null,
        category_ids: v.category_ids,
      },
    });
    setEditing(null);
    await refresh();
  }

  async function onUpdate(id: number, v: FormState) {
    await fetchJSON(`/api/v1/buckets/${id}`, {
      method: "PATCH",
      json: {
        name: v.name.trim(),
        icon: v.icon || null,
        color: v.color || null,
        sort_order: Number(v.sort_order) || 0,
        note: v.note.trim() || null,
        category_ids: v.category_ids,
      },
    });
    setEditing(null);
    await refresh();
  }

  async function onArchive(id: number, archived: boolean) {
    if (!archived && !confirm("Lưu trữ nhóm này?")) return;
    await fetchJSON(`/api/v1/buckets/${id}`, {
      method: "PATCH",
      json: { archived: !archived },
    });
    await refresh();
  }

  async function onDelete(b: Bucket) {
    if (!confirm(`Xoá hẳn nhóm "${b.name}"? (Nếu đang có allocation trong plan thì sẽ báo lỗi)`))
      return;
    try {
      await fetchJSON(`/api/v1/buckets/${b.id}`, { method: "DELETE" });
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">🪣 Nhóm phân bổ</h1>
          <p className="muted text-sm">
            Gom các danh mục chi tiêu thành nhóm mục đích (ví dụ Thiết yếu, Mong muốn, Tiết kiệm).
            Dùng trong Kế hoạch tháng để phân bổ thu nhập.
          </p>
        </div>
        <div className="flex gap-2">
          <label className="flex items-center gap-2 text-sm muted">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
            />
            Hiện đã lưu trữ
          </label>
          {editing !== "new" && (
            <button
              onClick={() => setEditing("new")}
              className="btn btn-grd-primary"
            >
              <Plus size={14} /> Thêm nhóm
            </button>
          )}
        </div>
      </div>

      {editing === "new" && (
        <BucketForm
          initial={emptyForm}
          allCategories={categories}
          usedByOther={usedByOther(null)}
          onSubmit={onCreate}
          onCancel={() => setEditing(null)}
          submitLabel="Tạo"
        />
      )}

      <div className="flex flex-col gap-2">
        {visible.length === 0 && (
          <div className="card muted text-sm">
            Chưa có nhóm nào. Bấm "Thêm nhóm" để tạo. Gợi ý 50/30/20: Thiết yếu / Mong muốn / Tiết kiệm.
          </div>
        )}
        {visible.map((b) => (
          <div key={b.id} className="card">
            {editing === b.id ? (
              <BucketForm
                initial={{
                  name: b.name,
                  icon: b.icon || "🪣",
                  color: b.color || "#16a34a",
                  sort_order: String(b.sort_order),
                  note: b.note || "",
                  category_ids: [...b.category_ids],
                }}
                allCategories={categories}
                usedByOther={usedByOther(b.id)}
                onSubmit={(v) => onUpdate(b.id, v)}
                onCancel={() => setEditing(null)}
                submitLabel="Lưu"
              />
            ) : (
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <span
                    className="w-9 h-9 flex items-center justify-center rounded-full text-lg shrink-0"
                    style={{ backgroundColor: b.color || "#1f2937" }}
                  >
                    {b.icon || "🪣"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{b.name}</span>
                      {b.archived && (
                        <span className="chip chip-muted">đã lưu trữ</span>
                      )}
                    </div>
                    {b.note && <div className="muted text-sm mt-0.5">{b.note}</div>}
                    <div className="mt-1 flex flex-wrap gap-1">
                      {b.category_ids.length === 0 ? (
                        <span className="text-xs muted italic">
                          chưa gán danh mục nào
                        </span>
                      ) : (
                        b.category_ids.map((cid) => {
                          const c = catById.get(cid);
                          return (
                            <span key={cid} className="chip chip-muted">
                              {c?.path || c?.name || `#${cid}`}
                            </span>
                          );
                        })
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button
                    onClick={() => setEditing(b.id)}
                    className="border border-[var(--border)] text-sm p-1.5 rounded hover:bg-[var(--border)]/40"
                    title="Sửa"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    onClick={() => onArchive(b.id, b.archived)}
                    className="border border-[var(--border)] text-sm p-1.5 rounded hover:bg-[var(--border)]/40"
                    title={b.archived ? "Mở lại" : "Lưu trữ"}
                  >
                    {b.archived ? (
                      <ArchiveRestore size={14} />
                    ) : (
                      <Archive size={14} />
                    )}
                  </button>
                  <button
                    onClick={() => onDelete(b)}
                    className="border border-[var(--border)] text-sm p-1.5 rounded hover:bg-red-900/40"
                    title="Xoá"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
