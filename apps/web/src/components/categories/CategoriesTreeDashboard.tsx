"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

import { fmtVND } from "@/lib/api";
import { PeriodTabs } from "@/components/dashboard/PeriodTabs";

type CategoryRow = {
  id: number;
  name: string;
  parent_id: number | null;
  path: string;
  kind: string;
  icon: string | null;
  color: string | null;
  total: number;
  count: number;
};

type TreeNode = CategoryRow & {
  children: TreeNode[];
  subtotal: number; // self + descendants
  subcount: number;
};

const KIND_META: Record<string, { label: string; color: string; icon: string }> = {
  expense: { label: "Chi tiêu", color: "#ef4444", icon: "📉" },
  income: { label: "Thu nhập", color: "#22c55e", icon: "📈" },
  transfer: { label: "Transfer", color: "#60a5fa", icon: "⇄" },
};

function buildTree(rows: CategoryRow[]): Record<string, TreeNode[]> {
  const byId = new Map<number, TreeNode>();
  const roots: Record<string, TreeNode[]> = {};
  for (const r of rows) {
    byId.set(r.id, {
      ...r,
      children: [],
      subtotal: r.total,
      subcount: r.count,
    });
  }
  for (const node of byId.values()) {
    if (node.parent_id && byId.has(node.parent_id)) {
      byId.get(node.parent_id)!.children.push(node);
    } else {
      (roots[node.kind] ||= []).push(node);
    }
  }
  // Compute subtotals bottom-up
  const accumulate = (n: TreeNode) => {
    for (const c of n.children) {
      accumulate(c);
      n.subtotal += c.subtotal;
      n.subcount += c.subcount;
    }
  };
  for (const kind of Object.keys(roots)) {
    roots[kind].forEach(accumulate);
    roots[kind].sort((a, b) => b.subtotal - a.subtotal);
    for (const r of roots[kind]) {
      const sortChildren = (n: TreeNode) => {
        n.children.sort((a, b) => b.subtotal - a.subtotal);
        n.children.forEach(sortChildren);
      };
      sortChildren(r);
    }
  }
  return roots;
}

export function CategoriesTreeDashboard({
  initialRows,
  period,
}: {
  initialRows: CategoryRow[];
  period: string;
}) {
  const router = useRouter();
  const [rows, setRows] = useState<CategoryRow[]>(initialRows);
  const [newName, setNewName] = useState("");
  const [newKind, setNewKind] = useState<"expense" | "income" | "transfer">("expense");
  const [newParentId, setNewParentId] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const r = await fetch(`/api/v1/categories/stats/all?period=${period}&kind=all`, {
      cache: "no-store",
    });
    setRows(await r.json());
    // Invalidate Server Component cache for the current route so that any
    // other data derived from categories (e.g. PlanProgressCard, sidebar)
    // refetches next time this page is navigated to.
    router.refresh();
  }, [period, router]);

  const addCategory = async () => {
    const name = newName.trim();
    if (!name) return;
    setErr(null);
    try {
      const r = await fetch("/api/v1/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          kind: newKind,
          parent_id: newParentId ? Number(newParentId) : null,
        }),
      });
      if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
      setNewName("");
      setNewParentId("");
      await refresh();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const deleteCategory = async (id: number, name: string) => {
    if (!confirm(`Xoá category "${name}"?`)) return;
    const r = await fetch(`/api/v1/categories/${id}`, { method: "DELETE" });
    if (!r.ok) {
      alert(`Không xoá được: ${await r.text()}`);
      return;
    }
    await refresh();
  };

  const tree = useMemo(() => buildTree(rows), [rows]);

  // KPIs
  const totalByKind = useMemo(() => {
    const sums: Record<string, number> = {};
    const counts: Record<string, number> = {};
    for (const r of rows) {
      if (!r.parent_id) {
        // already accumulated via subtree — but tree view doesn't give access to roots here easily.
      }
    }
    for (const roots of Object.values(tree)) {
      for (const r of roots) {
        sums[r.kind] = (sums[r.kind] || 0) + r.subtotal;
        counts[r.kind] = (counts[r.kind] || 0) + r.subcount;
      }
    }
    return { sums, counts };
  }, [tree, rows]);

  const renderNode = (node: TreeNode, depth: number, maxKind: number) => {
    const pct = maxKind ? (node.subtotal / maxKind) * 100 : 0;
    return (
      <div key={node.id}>
        <div
          className="group flex items-center gap-2 py-1 hover:bg-[var(--border)] -mx-2 px-2 rounded"
          style={{ paddingLeft: 8 + depth * 18 }}
        >
          {depth > 0 && <span className="muted">↳</span>}
          <span className="text-lg">{node.icon || "📁"}</span>
          <Link
            href={`/categories/${node.id}?period=${period}`}
            className="font-medium hover:underline flex-1 truncate"
            title={node.path}
          >
            {node.name}
          </Link>
          <span className="muted text-xs">({node.subcount})</span>
          <span className="font-mono text-sm min-w-[140px] text-right">
            {fmtVND(node.subtotal)}
          </span>
          <div className="w-24 h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
            <div
              className="h-full"
              style={{
                width: `${pct}%`,
                background: node.color || KIND_META[node.kind].color,
              }}
            />
          </div>
          <button
            onClick={() => deleteCategory(node.id, node.name)}
            className="opacity-0 group-hover:opacity-100 transition text-xs text-red-400 hover:text-red-300"
            title="Xoá"
          >
            ✕
          </button>
        </div>
        {node.children.map((c) =>
          renderNode(c, depth + 1, maxKind)
        )}
      </div>
    );
  };

  const expenseRoots = tree.expense || [];
  const incomeRoots = tree.income || [];
  const transferRoots = tree.transfer || [];
  const allFlat = rows.filter((r) => r.kind === newKind);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">📁 Categories</h1>
          <p className="muted text-sm">
            Cây phân loại. Click tên để xem detail riêng. Hover để xoá.
          </p>
        </div>
        <PeriodTabs current={period} />
      </div>

      {/* KPIs */}
      <section className="grid grid-cols-3 gap-4">
        {(["expense", "income", "transfer"] as const).map((k) => (
          <div key={k} className="card">
            <div className="muted text-xs uppercase">
              {KIND_META[k].icon} {KIND_META[k].label}
            </div>
            <div
              className="text-2xl font-semibold mt-1"
              style={{ color: KIND_META[k].color }}
            >
              {fmtVND(totalByKind.sums[k] || 0)}
            </div>
            <div className="muted text-xs mt-1">
              {totalByKind.counts[k] || 0} giao dịch
            </div>
          </div>
        ))}
      </section>

      {/* Add form */}
      <section className="card">
        <h2 className="font-semibold mb-2">Thêm category</h2>
        {err && <p className="text-red-400 text-sm mb-2">{err}</p>}
        <div className="flex flex-wrap gap-2 items-end">
          <label className="flex flex-col text-sm">
            <span className="muted">Tên</span>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="VD: Cà phê"
              className="field"
            />
          </label>
          <label className="flex flex-col text-sm">
            <span className="muted">Kind</span>
            <select
              value={newKind}
              onChange={(e) => {
                setNewKind(e.target.value as "expense" | "income" | "transfer");
                setNewParentId("");
              }}
              className="field"
            >
              <option value="expense">Chi tiêu</option>
              <option value="income">Thu nhập</option>
              <option value="transfer">Transfer</option>
            </select>
          </label>
          <label className="flex flex-col text-sm">
            <span className="muted">Parent (tuỳ chọn)</span>
            <select
              value={newParentId}
              onChange={(e) => setNewParentId(e.target.value)}
              className="field"
            >
              <option value="">— gốc —</option>
              {allFlat.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.path}
                </option>
              ))}
            </select>
          </label>
          <button onClick={addCategory} className="btn btn-grd-primary">
            + Tạo
          </button>
        </div>
      </section>

      {/* Trees */}
      <section className="grid md:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="font-semibold mb-2">
            📉 Chi tiêu ({expenseRoots.length} nhóm gốc)
          </h2>
          {expenseRoots.length === 0 ? (
            <p className="muted text-sm">Chưa có chi tiêu category.</p>
          ) : (
            <div className="space-y-0.5">
              {(() => {
                const maxK = Math.max(1, ...expenseRoots.map((r) => r.subtotal));
                return expenseRoots.map((r) => renderNode(r, 0, maxK));
              })()}
            </div>
          )}
        </div>
        <div className="space-y-4">
          <div className="card">
            <h2 className="font-semibold mb-2">
              📈 Thu nhập ({incomeRoots.length} nhóm gốc)
            </h2>
            {incomeRoots.length === 0 ? (
              <p className="muted text-sm">Chưa có thu nhập category.</p>
            ) : (
              <div className="space-y-0.5">
                {(() => {
                  const maxK = Math.max(1, ...incomeRoots.map((r) => r.subtotal));
                  return incomeRoots.map((r) => renderNode(r, 0, maxK));
                })()}
              </div>
            )}
          </div>
          <div className="card">
            <h2 className="font-semibold mb-2">
              ⇄ Transfer ({transferRoots.length})
            </h2>
            {transferRoots.length === 0 ? (
              <p className="muted text-sm">Chưa có transfer category.</p>
            ) : (
              <div className="space-y-0.5">
                {(() => {
                  const maxK = Math.max(1, ...transferRoots.map((r) => r.subtotal));
                  return transferRoots.map((r) => renderNode(r, 0, maxK));
                })()}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
