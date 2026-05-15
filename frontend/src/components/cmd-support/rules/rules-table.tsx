"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Column = { header: string; className?: string };
type Row = { key: string; cells: ReactNode[] };

type Props = {
  loading: boolean;
  empty: string;
  columns: Column[];
  rows: Row[];
};

export function RulesTable({ loading, empty, columns, rows }: Props) {
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              {columns.map((c, i) => (
                <th
                  key={i}
                  className={cn(
                    "text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground px-3 py-2",
                    c.className,
                  )}
                >
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center text-muted-foreground">
                  <span className="material-symbols-outlined animate-spin text-base mr-1 align-middle">
                    progress_activity
                  </span>
                  Đang tải…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center text-muted-foreground">
                  {empty}
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.key} className="border-t border-border align-top">
                  {row.cells.map((cell, i) => (
                    <td key={i} className={cn("px-3 py-3", columns[i]?.className)}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
