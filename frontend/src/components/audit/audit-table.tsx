"use client";

import React from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";

export type AuditLogEntry = {
  id: string;
  timestamp: string;
  action: string;
  principal_id: string;
  principal_name?: string;
  principal_email?: string;
  resource_type: string;
  resource_id?: string;
  decision: string;
  reason?: string;
};

type Props = {
  logs: AuditLogEntry[];
  loading: boolean;
};

export function AuditTable({ logs, loading }: Props) {
  if (loading) {
    return (
      <div className="bg-card rounded-xl border border-border shadow-sahara flex items-center justify-center py-16">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  if (logs.length === 0) {
    return (
      <div className="bg-card rounded-xl border border-border shadow-sahara">
        <EmptyState
          icon="policy"
          title="Không tìm thấy nhật ký"
          description="Các sự kiện kiểm soát truy cập sẽ xuất hiện tại đây."
        />
      </div>
    );
  }

  return (
    <div className="bg-card rounded-xl border border-border shadow-sahara overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="text-xs uppercase tracking-wider">Thời gian</TableHead>
            <TableHead className="text-xs uppercase tracking-wider">Người thực hiện</TableHead>
            <TableHead className="text-xs uppercase tracking-wider">Hành động</TableHead>
            <TableHead className="text-xs uppercase tracking-wider">Tài nguyên</TableHead>
            <TableHead className="text-xs uppercase tracking-wider">Quyết định</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {logs.map((log) => (
            <TableRow key={log.id} className="hover:bg-secondary/30">
              <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                {new Date(log.timestamp).toLocaleString()}
              </TableCell>
              <TableCell>
                <div className="flex flex-col">
                  <span className="text-sm font-medium">{log.principal_name || "System/Unknown"}</span>
                  <span className="text-xs text-muted-foreground">{log.principal_email || log.principal_id.slice(0, 8) + '...'}</span>
                </div>
              </TableCell>
              <TableCell>
                <Badge
                  variant="outline"
                  className={`text-xs font-mono font-normal ${
                    log.action.toLowerCase() === "create"
                      ? "border-green-200 text-green-700 bg-green-50/50"
                      : log.action.toLowerCase() === "delete"
                      ? "border-red-200 text-red-700 bg-red-50/50"
                      : "border-blue-200 text-blue-700 bg-blue-50/50"
                  }`}
                >
                  {log.action}
                </Badge>
              </TableCell>
              <TableCell>
                <div className="flex flex-col">
                  <span className="text-sm capitalize">{log.resource_type}</span>
                  {log.resource_id && (
                    <span className="text-xs text-muted-foreground font-mono">
                      {log.resource_id.length > 20 ? log.resource_id.slice(0, 8) + '...' : log.resource_id}
                    </span>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-col items-start gap-1">
                  <Badge
                    variant="outline"
                    className={`text-xs ${
                      log.decision.toLowerCase() === "allow"
                        ? "border-green-200 text-green-700 bg-green-50/50"
                        : "border-red-200 text-red-700 bg-red-50/50"
                    }`}
                  >
                    {log.decision.toUpperCase()}
                  </Badge>
                  {log.reason && (
                    <span className="text-xs text-muted-foreground max-w-[200px] truncate" title={log.reason}>
                      {log.reason}
                    </span>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
