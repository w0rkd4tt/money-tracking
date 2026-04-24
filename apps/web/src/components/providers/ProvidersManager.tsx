"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Pencil,
  Plus,
  RefreshCw,
  Star,
  Trash2,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

type Provider = {
  id: string; // "builtin:name" or "custom:123"
  source: "builtin" | "custom";
  name: string;
  endpoint: string;
  model: string;
  timeout_sec: number;
  enabled: boolean;
  is_default: boolean;
  has_api_key: boolean;
};

type TestResult = { ok: boolean; detail: string };

type EditState = {
  endpoint: string;
  model: string;
  api_key: string;
  timeout_sec: number;
  enabled: boolean;
  is_default: boolean;
};

const emptyNew = {
  name: "",
  endpoint: "",
  model: "",
  api_key: "",
  timeout_sec: 120,
  is_default: false,
  enabled: true,
};

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
  if (!r.ok) {
    let detail = await r.text();
    try {
      detail = JSON.parse(detail).detail ?? detail;
    } catch {
      // keep raw text
    }
    throw new Error(`${r.status}: ${detail}`);
  }
  if (r.status === 204) return undefined as T;
  return r.json();
}

export function ProvidersManager({
  initialProviders,
}: {
  initialProviders: Provider[];
}) {
  const [providers, setProviders] = useState<Provider[]>(initialProviders);
  const [tests, setTests] = useState<Record<string, TestResult>>({});
  const [testing, setTesting] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // Inline edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditState | null>(null);
  const [editHasSavedKey, setEditHasSavedKey] = useState(false);
  const [saving, setSaving] = useState(false);

  // Add-new state
  const [addOpen, setAddOpen] = useState(false);
  const [newProvider, setNewProvider] = useState(emptyNew);
  const [adding, setAdding] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchJSON<Provider[]>("/api/v1/llm/providers");
      setProviders(data);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  // Initial per-provider ping on mount so the status column is populated.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (const p of initialProviders) {
        try {
          const r = await fetchJSON<{ ok: boolean; detail: string }>(
            `/api/v1/llm/providers/${encodeURIComponent(p.name)}/test`,
            { method: "POST" }
          );
          if (cancelled) return;
          setTests((x) => ({ ...x, [p.name]: { ok: r.ok, detail: r.detail } }));
        } catch {
          if (cancelled) return;
          setTests((x) => ({ ...x, [p.name]: { ok: false, detail: "error" } }));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initialProviders]);

  const flashInfo = (msg: string) => {
    setInfo(msg);
    setTimeout(() => setInfo(null), 3000);
  };

  async function testOne(name: string) {
    setTesting(name);
    setErr(null);
    try {
      const r = await fetchJSON<{ ok: boolean; detail: string }>(
        `/api/v1/llm/providers/${encodeURIComponent(name)}/test`,
        { method: "POST" }
      );
      setTests((x) => ({ ...x, [name]: { ok: r.ok, detail: r.detail } }));
    } catch (e) {
      setTests((x) => ({ ...x, [name]: { ok: false, detail: "error" } }));
      setErr((e as Error).message);
    } finally {
      setTesting(null);
    }
  }

  async function testAll() {
    for (const p of providers.filter((x) => x.enabled)) {
      await testOne(p.name);
    }
  }

  async function onDelete(p: Provider) {
    if (p.source !== "custom") return;
    if (!confirm(`Xoá provider "${p.name}"?`)) return;
    const customId = p.id.split(":")[1];
    try {
      await fetchJSON(`/api/v1/llm/providers/${customId}`, { method: "DELETE" });
      await refresh();
      flashInfo(`Đã xoá ${p.name}`);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  function beginEdit(p: Provider) {
    setEditingId(p.id);
    setEditHasSavedKey(p.has_api_key);
    setEditForm({
      endpoint: p.endpoint,
      model: p.model,
      api_key: "",
      timeout_sec: p.timeout_sec,
      enabled: p.enabled,
      is_default: p.is_default,
    });
    setErr(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditForm(null);
  }

  async function saveEdit() {
    if (!editingId || !editForm) return;
    setErr(null);
    setSaving(true);
    try {
      // Only include api_key if user typed something new
      const payload: Record<string, unknown> = {
        endpoint: editForm.endpoint.trim(),
        model: editForm.model.trim(),
        timeout_sec: Number(editForm.timeout_sec) || 120,
        enabled: editForm.enabled,
        is_default: editForm.is_default,
      };
      if (editForm.api_key.trim()) payload.api_key = editForm.api_key.trim();

      if (editingId.startsWith("custom:")) {
        const customId = editingId.split(":")[1];
        await fetchJSON(`/api/v1/llm/providers/${customId}`, {
          method: "PATCH",
          json: payload,
        });
      } else {
        // Builtin edit → create/update the override row
        const builtinName = editingId.split(":")[1];
        const existingOverride = providers.find(
          (x) => x.source === "custom" && x.name === builtinName
        );
        if (existingOverride) {
          const customId = existingOverride.id.split(":")[1];
          await fetchJSON(`/api/v1/llm/providers/${customId}`, {
            method: "PATCH",
            json: payload,
          });
        } else {
          await fetchJSON("/api/v1/llm/providers", {
            json: { name: builtinName, ...payload },
          });
        }
      }
      await refresh();
      cancelEdit();
      flashInfo("Đã lưu");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function onCreate() {
    if (!newProvider.name.trim() || !newProvider.endpoint.trim() || !newProvider.model.trim()) {
      setErr("Cần điền tên, endpoint và model");
      return;
    }
    setErr(null);
    setAdding(true);
    try {
      const payload: Record<string, unknown> = {
        name: newProvider.name.trim(),
        endpoint: newProvider.endpoint.trim(),
        model: newProvider.model.trim(),
        timeout_sec: Number(newProvider.timeout_sec) || 120,
        enabled: newProvider.enabled,
        is_default: newProvider.is_default,
      };
      if (newProvider.api_key.trim()) payload.api_key = newProvider.api_key.trim();
      await fetchJSON("/api/v1/llm/providers", { json: payload });
      await refresh();
      setNewProvider(emptyNew);
      setAddOpen(false);
      flashInfo(`Đã thêm provider "${newProvider.name}"`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setAdding(false);
    }
  }

  const defaultProvider = useMemo(
    () => providers.find((p) => p.is_default),
    [providers]
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Zap size={22} className="text-[var(--primary)]" /> LLM Providers
          </h1>
          <p className="muted text-sm mt-1">
            Quản lý các nhà cung cấp LLM dùng cho Chat. Builtin provider được khai
            báo qua env (m1ultra, galaxy_one). Custom provider lưu trong DB với{" "}
            <code className="text-xs bg-[var(--border)] px-1 py-0.5 rounded">
              api_key
            </code>{" "}
            mã hoá AES-GCM.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={testAll} className="btn btn-ghost" title="Test tất cả">
            <RefreshCw size={14} /> Test tất cả
          </button>
          {!addOpen && (
            <button onClick={() => setAddOpen(true)} className="btn btn-grd-primary">
              <Plus size={14} /> Thêm provider
            </button>
          )}
        </div>
      </div>

      {defaultProvider && (
        <div className="card-tight card flex items-center gap-2 text-sm">
          <Star size={14} className="text-[var(--warning)]" fill="currentColor" />
          <span>
            Default hiện tại: <strong>{defaultProvider.name}</strong>{" "}
            <span className="muted">({defaultProvider.model})</span>
          </span>
        </div>
      )}

      {err && (
        <div className="card-tight card border border-red-900/60 bg-red-950/30 flex items-start gap-2 text-sm">
          <AlertTriangle size={16} className="text-[var(--danger)] shrink-0 mt-0.5" />
          <div className="flex-1">{err}</div>
          <button
            onClick={() => setErr(null)}
            className="btn-icon"
            title="Đóng"
          >
            <X size={14} />
          </button>
        </div>
      )}
      {info && (
        <div className="card-tight card border border-emerald-900/60 bg-emerald-950/20 text-sm">
          <span className="text-[var(--success)]">✓ {info}</span>
        </div>
      )}

      {addOpen && (
        <div className="card flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Thêm custom provider</h2>
            <button
              onClick={() => {
                setAddOpen(false);
                setNewProvider(emptyNew);
                setErr(null);
              }}
              className="btn-icon"
              title="Huỷ"
            >
              <X size={14} />
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 text-sm">
              <span className="muted">Tên (unique, sẽ normalize về snake_case)</span>
              <input
                className="field"
                placeholder="openrouter_claude"
                value={newProvider.name}
                onChange={(e) =>
                  setNewProvider((x) => ({ ...x, name: e.target.value }))
                }
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="muted">Endpoint (chat URL đầy đủ)</span>
              <input
                className="field"
                placeholder="https://openrouter.ai/api/v1/chat/completions"
                value={newProvider.endpoint}
                onChange={(e) =>
                  setNewProvider((x) => ({ ...x, endpoint: e.target.value }))
                }
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="muted">Model</span>
              <input
                className="field"
                placeholder="anthropic/claude-3.5-sonnet"
                value={newProvider.model}
                onChange={(e) =>
                  setNewProvider((x) => ({ ...x, model: e.target.value }))
                }
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="muted">API key (tuỳ chọn, mã hoá trước khi lưu)</span>
              <input
                type="password"
                className="field"
                placeholder="sk-..."
                value={newProvider.api_key}
                onChange={(e) =>
                  setNewProvider((x) => ({ ...x, api_key: e.target.value }))
                }
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="muted">Timeout (giây)</span>
              <input
                type="number"
                min={1}
                max={600}
                className="field"
                value={newProvider.timeout_sec}
                onChange={(e) =>
                  setNewProvider((x) => ({
                    ...x,
                    timeout_sec: Number(e.target.value || "120"),
                  }))
                }
              />
            </label>
            <div className="flex items-center gap-4 text-sm pt-6">
              <label className="inline-flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={newProvider.enabled}
                  onChange={(e) =>
                    setNewProvider((x) => ({ ...x, enabled: e.target.checked }))
                  }
                />
                Enabled
              </label>
              <label className="inline-flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={newProvider.is_default}
                  onChange={(e) =>
                    setNewProvider((x) => ({ ...x, is_default: e.target.checked }))
                  }
                />
                Đặt làm default
              </label>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={onCreate}
              disabled={adding}
              className="btn btn-grd-primary"
            >
              {adding ? "Đang tạo…" : "Tạo provider"}
            </button>
            <button
              onClick={() => {
                setAddOpen(false);
                setNewProvider(emptyNew);
                setErr(null);
              }}
              className="btn btn-ghost"
            >
              Huỷ
            </button>
          </div>
        </div>
      )}

      <div className="card !p-0 overflow-auto">
        <table className="table-clean">
          <thead>
            <tr>
              <th>Tên</th>
              <th>Nguồn</th>
              <th>Model</th>
              <th>Endpoint</th>
              <th>Trạng thái</th>
              <th className="text-right">Hành động</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => {
              const isEditing = editingId === p.id;
              const status = tests[p.name];
              return (
                <>
                  <tr key={p.id}>
                    <td>
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium">{p.name}</span>
                        {p.is_default && (
                          <Star
                            size={12}
                            className="text-[var(--warning)] shrink-0"
                            fill="currentColor"
                          />
                        )}
                        {!p.enabled && (
                          <span className="chip chip-muted">disabled</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span
                        className={
                          p.source === "builtin"
                            ? "chip chip-info"
                            : "chip chip-primary"
                        }
                      >
                        {p.source}
                      </span>
                    </td>
                    <td className="font-mono text-xs">{p.model}</td>
                    <td
                      className="muted text-xs max-w-[320px] truncate"
                      title={p.endpoint}
                    >
                      {p.endpoint}
                    </td>
                    <td>
                      {testing === p.name ? (
                        <span className="muted text-xs inline-flex items-center gap-1">
                          <RefreshCw size={12} className="animate-spin" /> đang test
                        </span>
                      ) : status ? (
                        <span
                          className={`inline-flex items-center gap-1.5 text-xs ${
                            status.ok ? "text-[var(--success)]" : "text-[var(--danger)]"
                          }`}
                        >
                          {status.ok ? (
                            <CheckCircle2 size={13} />
                          ) : (
                            <XCircle size={13} />
                          )}
                          {status.ok ? "OK" : "Lỗi"}
                          <span className="muted">({status.detail})</span>
                        </span>
                      ) : (
                        <span className="muted text-xs">chưa test</span>
                      )}
                    </td>
                    <td>
                      <div className="flex gap-1 justify-end">
                        <button
                          onClick={() => testOne(p.name)}
                          disabled={testing === p.name}
                          className="btn-icon"
                          title="Test"
                        >
                          <RefreshCw size={13} />
                        </button>
                        <button
                          onClick={() => (isEditing ? cancelEdit() : beginEdit(p))}
                          className="btn-icon"
                          title={isEditing ? "Huỷ sửa" : "Sửa"}
                        >
                          {isEditing ? <X size={13} /> : <Pencil size={13} />}
                        </button>
                        {p.source === "custom" && (
                          <button
                            onClick={() => onDelete(p)}
                            className="btn-icon hover:!text-[var(--danger)]"
                            title="Xoá"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {isEditing && editForm && (
                    <tr key={`${p.id}-edit`}>
                      <td colSpan={6} className="!p-4 bg-[var(--bg)]/40">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          <label className="flex flex-col gap-1 text-sm">
                            <span className="muted">Endpoint</span>
                            <input
                              className="field"
                              value={editForm.endpoint}
                              onChange={(e) =>
                                setEditForm((x) =>
                                  x ? { ...x, endpoint: e.target.value } : x
                                )
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-sm">
                            <span className="muted">Model</span>
                            <input
                              className="field"
                              value={editForm.model}
                              onChange={(e) =>
                                setEditForm((x) =>
                                  x ? { ...x, model: e.target.value } : x
                                )
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-sm">
                            <span className="muted">
                              API key{" "}
                              {editHasSavedKey && (
                                <span className="text-xs">
                                  · đang có key, để trống = giữ nguyên
                                </span>
                              )}
                            </span>
                            <input
                              type="password"
                              className="field"
                              placeholder={
                                editHasSavedKey
                                  ? "••••••••••  (để trống = giữ nguyên)"
                                  : "sk-... (tuỳ chọn)"
                              }
                              value={editForm.api_key}
                              onChange={(e) =>
                                setEditForm((x) =>
                                  x ? { ...x, api_key: e.target.value } : x
                                )
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-sm">
                            <span className="muted">Timeout (giây)</span>
                            <input
                              type="number"
                              min={1}
                              max={600}
                              className="field"
                              value={editForm.timeout_sec}
                              onChange={(e) =>
                                setEditForm((x) =>
                                  x
                                    ? {
                                        ...x,
                                        timeout_sec:
                                          Number(e.target.value || "120"),
                                      }
                                    : x
                                )
                              }
                            />
                          </label>
                          <div className="flex items-center gap-4 text-sm">
                            <label className="inline-flex items-center gap-1.5">
                              <input
                                type="checkbox"
                                checked={editForm.enabled}
                                onChange={(e) =>
                                  setEditForm((x) =>
                                    x ? { ...x, enabled: e.target.checked } : x
                                  )
                                }
                              />
                              Enabled
                            </label>
                            <label className="inline-flex items-center gap-1.5">
                              <input
                                type="checkbox"
                                checked={editForm.is_default}
                                onChange={(e) =>
                                  setEditForm((x) =>
                                    x
                                      ? { ...x, is_default: e.target.checked }
                                      : x
                                  )
                                }
                              />
                              Default
                            </label>
                          </div>
                        </div>
                        <div className="flex gap-2 mt-3">
                          <button
                            onClick={saveEdit}
                            disabled={saving}
                            className="btn btn-grd-primary"
                          >
                            {saving ? "Đang lưu…" : "Lưu"}
                          </button>
                          <button onClick={cancelEdit} className="btn btn-ghost">
                            Huỷ
                          </button>
                        </div>
                        {p.source === "builtin" && (
                          <p className="muted text-xs mt-2">
                            Sửa builtin provider sẽ tạo/ghi đè custom row cùng tên.
                            Xoá row đó để quay về config env.
                          </p>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
            {providers.length === 0 && (
              <tr>
                <td colSpan={6} className="py-6 muted text-center">
                  Chưa có provider nào.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
