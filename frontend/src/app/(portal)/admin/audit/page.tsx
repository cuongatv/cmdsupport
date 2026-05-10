"use client";

import React, { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { AuditTable, AuditLogEntry } from "@/components/audit/audit-table";
import { Button } from "@/components/ui/button";

type AuditResponse = {
  items: AuditLogEntry[];
  total: number;
  page: number;
  size: number;
  pages: number;
};

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const loadLogs = useCallback(async (pageNum: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api<AuditResponse>(`/api/audit/log?page=${pageNum}&size=20`);
      setLogs(data.items);
      setTotalPages(data.pages);
      setPage(data.page);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể tải nhật ký kiểm toán");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLogs(1);
  }, [loadLogs]);

  return (
    <>
      <PageHeader
        title="Nhật ký kiểm toán"
        description="Xem lại các quyết định kiểm soát truy cập và đánh giá chính sách trên hệ thống."
        action={
          <Button
            variant="outline"
            onClick={() => loadLogs(1)}
            disabled={loading}
          >
            <span className={`material-symbols-outlined text-base mr-2 ${loading ? 'animate-spin' : ''}`}>
              refresh
            </span>
            Làm mới
          </Button>
        }
      />

      {error && (
        <div className="text-sm text-destructive bg-destructive/10 px-4 py-3 rounded-lg flex items-center gap-2 mb-6">
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </div>
      )}

      <div className="flex flex-col gap-4">
        <AuditTable logs={logs} loading={loading} />

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between bg-card rounded-xl border border-border px-4 py-3">
            <span className="text-sm text-muted-foreground">
              Trang {page} / {totalPages}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || loading}
                onClick={() => loadLogs(page - 1)}
              >
                Trước
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || loading}
                onClick={() => loadLogs(page + 1)}
              >
                Tiếp
              </Button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
